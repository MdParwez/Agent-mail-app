from __future__ import annotations
import json, re
from typing import List, Dict, Any
from app.llm.gemini_client import GeminiClient

# PII regex heuristics
RE_CC = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
RE_PNR = re.compile(r"\b([A-Z0-9]{6,8})\b")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_PHONE = re.compile(r"\+?\d[\d\s\-()]{8,}")

def detect_pii(text: str) -> List[str]:
    hits = []
    if RE_CC.search(text): hits.append("credit_card_like_number")
    if RE_EMAIL.search(text): hits.append("email_address")
    if RE_PHONE.search(text): hits.append("phone_number_like")
    for m in RE_PNR.findall(text):
        if m.isupper() and any(ch.isdigit() for ch in m):
            hits.append("booking_reference_like"); break
    return hits

def redact_pii(text: str) -> str:
    text = RE_CC.sub("[redacted_card]", text)
    text = RE_EMAIL.sub("[redacted_email]", text)
    text = RE_PHONE.sub("[redacted_phone]", text)
    # cautious PNR redaction (all-caps mix of letters/digits length 6-8)
    return re.sub(r"\b[A-Z0-9]{6,8}\b", "[redacted_ref]", text)

_VALIDATOR_PROMPT = """You are a strict validator for airline support replies.
Return ONLY JSON with keys:
- is_valid: boolean
- reason: string
- tone_ok: boolean
- grounded_ok: boolean

Rule: grounded_ok=true only if the DRAFT strictly aligns with POLICY content.
Tone must be polite and concise.

POLICY:
---
{context}
---

DRAFT:
---
{draft}
---
JSON ONLY:
"""

def _loose_json_parse(s: str):
    try:
        return json.loads(s.strip())
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            try: return json.loads(m.group(0))
            except Exception: return None
        return None

def validate_with_gemini(llm: GeminiClient, context: List[str], draft: str) -> Dict[str, Any]:
    prompt = _VALIDATOR_PROMPT.format(context="\n---\n".join(context), draft=draft)
    for _ in range(2):
        raw = llm.generate(prompt)
        obj = _loose_json_parse(raw or "")
        if isinstance(obj, dict) and {"is_valid","reason","tone_ok","grounded_ok"} <= set(obj.keys()):
            return obj
        prompt += "\nRespond JSON only. No prose."
    return {"is_valid": False, "reason": "validator_json_parse_error", "tone_ok": False, "grounded_ok": False}
