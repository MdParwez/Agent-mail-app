from __future__ import annotations
from app.graph.state import AgentState
from app.graph import deps
from app.llm.validators import detect_pii, validate_with_gemini

DRAFT_PROMPT = """You are a helpful airline support agent for Team Indigo.
Use ONLY the policy context below. If the answer is not present, say you'll escalate.
Do NOT invent details. Be concise, polite, professional.
NEVER echo or reveal any personal data (emails, booking codes, phone, CC). If present in the user text, REDACT it as [REDACTED].  
If PII was in the user request, reply with general policy info but escalate to human review.

Always close the reply with:
Sincerely,
Team Indigo

Policy Context:
---
{context}
---

Customer email:
---
{email}
---

Write a concise reply strictly grounded in the policy. If policy doesn't cover it, say you'll escalate to a human agent.
"""


def retrieve_context(state: AgentState) -> AgentState:
    ctx = deps.retrieve(state["email_text"], k=4)
    state["retrieved_docs"] = ctx
    deps.log_event({
        "message_id": state["message_id"],
        "from_addr": state["from_addr"],
        "subject": state["subject"],
        "decision": "RETRIEVE",
        "reason": "Retrieved policy context",
        "matched_keywords": state.get("matched_keywords", []),
        "context_preview": ctx[:2]
    })
    return state

def draft_reply(state: AgentState) -> AgentState:
    prompt = DRAFT_PROMPT.format(
        context="\n".join(state["retrieved_docs"]),
        email=state["email_text"]
    )
    draft = deps.LLM.generate(prompt)
    state["draft_reply"] = draft
    deps.log_event({
        "message_id": state["message_id"],
        "from_addr": state["from_addr"],          # <<< keep for UI
        "subject": state["subject"],              # <<< keep for UI
        "decision": "DRAFT",
        "reason": "Draft generated",
        "draft_preview": (draft or "")[:800]
    })
    return state

# def validate_reply(state: AgentState) -> AgentState:
#     draft = state.get("draft_reply", "") or ""
#     ctx = state.get("retrieved_docs", []) or []
#     v = validate_with_gemini(deps.LLM, ctx, draft)

#     pii_hits = detect_pii(draft)
#     valid = bool(v.get("is_valid")) and bool(v.get("tone_ok")) and bool(v.get("grounded_ok")) and not pii_hits

#     state["validation"] = v
#     state["validation"]["pii"] = pii_hits

#     state["decision"] = "REWRITE"
#     state["reason"] = v.get("reason", "")
#     if valid:
#         state["decision"] = "REPLY"
#         state["reason"] = "Validation passed"

#     deps.log_event({
#         "message_id": state["message_id"],
#         "from_addr": state["from_addr"],          # <<< keep for UI
#         "subject": state["subject"],              # <<< keep for UI
#         "decision": "VALIDATED" if valid else "REWRITE",
#         "reason": state["reason"],
#         "pii": pii_hits
#     })
#     return state


def validate_reply(state: AgentState) -> AgentState:
    """
    - Valid = validator says ok (grounded + tone) AND draft has no PII.
    - If the *incoming request* had PII, we still allow the reply (with redaction),
      but we mark state['pii_in_request'] so send_email() will escalate-after-reply.
    """
    draft = state.get("draft_reply", "") or ""
    ctx = state.get("retrieved_docs", []) or []

    # 1) run model validator (JSON-only, robust)
    v = validate_with_gemini(deps.LLM, ctx, draft)

    # 2) PII detection (request vs. draft)
    pii_in_request = detect_pii(state.get("email_text", "") or "")
    pii_in_draft   = detect_pii(draft)

    # 3) validity check
    valid_core = bool(v.get("is_valid")) and bool(v.get("tone_ok")) and bool(v.get("grounded_ok"))
    # never accept a draft that still contains PII
    valid = valid_core and not pii_in_draft

    # persist validator + pii results on state
    state["validation"] = v
    state["validation"]["pii_request"] = pii_in_request
    state["validation"]["pii_draft"]   = pii_in_draft

    # let send_email() know whether to escalate-after-reply
    # (we reply with general policy, redacted; then add REVIEW label)
    state["pii_in_request"] = bool(pii_in_request)

    # 4) decide next step
    if valid:
        # reply is fine; if request had PII we'll escalate after sending
        state["decision"] = "REPLY"
        state["reason"] = "Validation passed" + (" (PII in request: will escalate after reply)" if pii_in_request else "")
        log_decision = "VALIDATED"
    else:
        # ask model to fix issues (will trigger rewrite node)
        state["decision"] = "REWRITE"
        # prefer validator reason; if PII in draft, make it explicit
        state["reason"] = v.get("reason", "") or ("PII found in draft" if pii_in_draft else "Rewrite required")
        log_decision = "REWRITE"

    # 5) log (include from/subject for UI)
    deps.log_event({
        "message_id": state["message_id"],
        "from_addr": state.get("from_addr", ""),
        "subject": state.get("subject", ""),
        "decision": log_decision,
        "reason": state["reason"],
        "pii_request": pii_in_request,
        "pii_draft": pii_in_draft,
    })
    return state

def rewrite_reply(state: AgentState) -> AgentState:
    fb = state.get("reason") or state.get("validation", {}).get("reason", "Fix issues.")
    fix_prompt = f"""Revise the reply to fix issues: {fb}
Stay strictly within policy context below. Never include PII. Redact any PII as [REDACTED].
---
{chr(10).join(state.get("retrieved_docs", []))}
---
Original reply:
---
{state.get("draft_reply","")}
---
New reply (concise, polite):"""
    state["draft_reply"] = deps.LLM.generate(fix_prompt)
    state["rewrite_count"] = int(state.get("rewrite_count", 0)) + 1
    deps.log_event({
        "message_id": state["message_id"],
        "from_addr": state["from_addr"],          # <<< added
        "subject": state["subject"],              # <<< added
        "decision": "REWRITE",
        "reason": f"Rewrite #{state['rewrite_count']}"
    })
    return state

def send_email(state: AgentState) -> AgentState:
    escalate_after = bool(state.get("pii_in_request"))
    deps.send_reply(
        state["from_addr"],
        state["subject"],
        state["draft_reply"],
        state["message_id"],
        escalate_after=escalate_after
    )
    state["final_reply"] = state["draft_reply"]
    state["decision"] = "REPLY"
    state["reason"] = "Reply sent" + (" (escalated for PII review)" if escalate_after else "")
    deps.log_event({
        "message_id": state["message_id"],
        "from_addr": state["from_addr"],          # <<< added
        "subject": state["subject"],              # <<< added
        "decision": "REPLY",
        "reason": state["reason"]
    })
    return state

def escalate(state: AgentState) -> AgentState:
    deps.escalate(state["message_id"])
    state["decision"] = "ESCALATE"
    state["reason"] = "Failed validation after 3 attempts or PII detected."
    deps.log_event({
        "message_id": state["message_id"],
        "from_addr": state["from_addr"],          # <<< added
        "subject": state["subject"],              # <<< added
        "decision": "ESCALATE",
        "reason": state["reason"]
    })
    return state
