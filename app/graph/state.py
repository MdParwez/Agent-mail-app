from __future__ import annotations
from typing import List, TypedDict, Dict, Any

class AgentState(TypedDict, total=False):
    message_id: str
    from_addr: str
    subject: str
    email_text: str            # subject + body combined
    matched_keywords: List[str]

    retrieved_docs: List[str]  # RAG context
    draft_reply: str

    validation: Dict[str, Any] # {is_valid, reason, tone_ok, grounded_ok, pii: [...]}
    rewrite_count: int

    decision: str              # "REWRITE" | "REPLY" | "ESCALATE" | "SKIP"
    reason: str
    final_reply: str
