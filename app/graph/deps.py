from __future__ import annotations
import os, json, time, numpy as np
from typing import List, Dict, Any
from rich import print as rprint
from app.core import config
from app.email import gmail_client

SERVICE = None
LLM = None
LABEL_IDS = {}
INDEX = None  # {"texts": List[str], "embeds": np.ndarray} OR a DB/collection

def set_runtime(service, llm, label_ids, index):
    global SERVICE, LLM, LABEL_IDS, INDEX
    SERVICE = service
    LLM = llm
    LABEL_IDS = label_ids
    INDEX = index

def log_event(event: dict):
    os.makedirs(os.path.dirname(config.LOGS_PATH), exist_ok=True)
    event["ts"] = event.get("ts") or time.time()
    with open(config.LOGS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # pretty console echo
    decision = (event.get("decision") or "LOG").upper()
    subject  = event.get("subject", "")
    reason   = event.get("reason", "")
    if decision == "REPLY":
        rprint(f"[bold green]REPLY[/]  • {subject}  — {reason}")
    elif decision == "ESCALATE":
        rprint(f"[bold yellow]ESCALATE[/] • {subject}  — {reason}")
    elif decision == "SKIP":
        rprint(f"[dim]SKIP[/]   • {subject}  — {reason}")
    elif decision == "RETRIEVE":
        rprint(f"[cyan]RETRIEVE[/] • {subject}")
    elif decision == "DRAFT":
        rprint(f"[cyan]DRAFT[/] • {subject}")
    elif decision == "REWRITE":
        rprint(f"[magenta]REWRITE[/] • {subject}  — {reason}")
    elif decision == "VALIDATED":
        rprint(f"[blue]VALIDATED[/] • {subject}  — {reason}")
    else:
        rprint(f"[white]{decision}[/] • {subject}  — {reason}")

def retrieve(query: str, k: int = 4) -> List[str]:
    qv = LLM.embed([query], task="RETRIEVAL_QUERY", dim=768)[0]
    A = INDEX["embeds"]
    q = np.array(qv)
    A_norm = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
    q_norm = q / (np.linalg.norm(q) + 1e-9)
    sims = A_norm @ q_norm
    topk = sims.argsort()[-k:][::-1]
    return [INDEX["texts"][i] for i in topk]

def send_reply(to_addr: str, subject: str, body: str, msg_id: str, escalate_after: bool = False):
    gmail_client.send_reply(SERVICE, to_addr=to_addr, subject=f"Re: {subject}", body=body)
    add = [LABEL_IDS.get(config.LABEL_OUT, config.LABEL_OUT)]
    if escalate_after:
        add.append(LABEL_IDS.get(config.LABEL_REVIEW, config.LABEL_REVIEW))
    gmail_client.modify_labels(
        SERVICE, msg_id,
        add=add,
        remove=["UNREAD", LABEL_IDS.get(config.LABEL_IN, config.LABEL_IN)]
    )

def escalate(msg_id: str):
    gmail_client.modify_labels(
        SERVICE, msg_id,
        add=[LABEL_IDS.get(config.LABEL_REVIEW, config.LABEL_REVIEW)],
        remove=["UNREAD", LABEL_IDS.get(config.LABEL_IN, config.LABEL_IN)]
    )

def mark_scanned(msg_id: str):
    gmail_client.modify_labels(
        SERVICE, msg_id,
        add=[LABEL_IDS.get(config.LABEL_SCANNED, config.LABEL_SCANNED)],
        remove=["UNREAD", LABEL_IDS.get(config.LABEL_IN, config.LABEL_IN)]
    )
