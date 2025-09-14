from __future__ import annotations
from langgraph.graph import StateGraph, END
from app.graph.state import AgentState
from app.graph.nodes import retrieve_context, draft_reply, validate_reply, rewrite_reply, send_email, escalate

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("retrieve_context", retrieve_context)
    g.add_node("draft_reply", draft_reply)
    g.add_node("validate_reply", validate_reply)
    g.add_node("rewrite_reply", rewrite_reply)
    g.add_node("send_email", send_email)
    g.add_node("escalate", escalate)

    g.set_entry_point("retrieve_context")
    g.add_edge("retrieve_context", "draft_reply")
    g.add_edge("draft_reply", "validate_reply")

    def route(state: AgentState):
        v = state.get("validation", {}) or {}
        ok = bool(v.get("is_valid")) and bool(v.get("tone_ok")) and bool(v.get("grounded_ok")) and not v.get("pii")
        if ok:
            return "send_email"
        if int(state.get("rewrite_count", 0)) < 2:
            return "rewrite_reply"
        return "escalate"

    g.add_conditional_edges("validate_reply", route, {
        "send_email": "send_email",
        "rewrite_reply": "rewrite_reply",
        "escalate": "escalate",
    })

    g.add_edge("rewrite_reply", "validate_reply")
    g.add_edge("send_email", END)
    g.add_edge("escalate", END)

    return g.compile()
