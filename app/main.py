from __future__ import annotations

import asyncio, json, os, re
from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel
from rich import print as rprint

from app.core import config
from app.email import gmail_client
from app.llm.gemini_client import GeminiClient
from app.llm.validators import detect_pii
from app.graph import deps
from app.graph.build_graph import build_graph

SERVICE = None
LLM = None
KEYWORDS = None
INDEX = None
LABEL_IDS = {}
GRAPH = None  # compiled LangGraph app

app = FastAPI(title="Email Agent (LangGraph + Gemini)")

def load_keywords():
    if not os.path.exists(config.KEYWORDS_JSON):
        raise FileNotFoundError(f"keywords json not found at {config.KEYWORDS_JSON}")
    return json.loads(open(config.KEYWORDS_JSON, "r", encoding="utf-8").read())

def re_split_words(s: str):
    return re.sub(r"[^a-z0-9]+", " ", s).split()

def subject_matches(subject: str, kw: dict) -> List[str]:
    subject_norm = subject.lower()
    matched = set()
    for p in kw.get("phrases", []):
        if len(p) >= 5 and p in subject_norm:
            matched.add(p)
    words = set(re_split_words(subject_norm))
    for u in kw.get("unigrams", []):
        if u in words:
            matched.add(u)
    return sorted(matched)

def extract_text_body(msg) -> str:
    return gmail_client.extract_text_body(msg)

def build_index(llm: GeminiClient):
    # Load or build a small NPZ index (already batched/backoff in client)
    if os.path.exists(config.INDEX_NPZ) and os.path.exists(config.INDEX_CHUNKS):
        import numpy as np
        data = json.loads(open(config.INDEX_CHUNKS, "r", encoding="utf-8").read())
        arr = np.load(config.INDEX_NPZ)
        return {"texts": data["texts"], "embeds": arr["embeds"]}

    import numpy as np, re as _re, math
    md = open(config.POLICY_MD, "r", encoding="utf-8").read()
    texts = [_c.strip() for _c in _re.split(r"\n(?=#+\s)|\n{2,}", md) if _c.strip()]

    max_items = 95
    if len(texts) > max_items:
        group = (len(texts) + max_items - 1) // max_items
        texts = ["\n\n".join(texts[i:i+group]) for i in range(0, len(texts), group)]

    embeds = llm.embed(texts, task="RETRIEVAL_DOCUMENT", dim=768)
    np.savez(config.INDEX_NPZ, embeds=np.array(embeds))
    json.dump({"texts": texts}, open(config.INDEX_CHUNKS, "w", encoding="utf-8"), indent=2)
    return {"texts": texts, "embeds": np.array(embeds)}

async def process_message_with_graph(msg: Dict[str, Any]):
    headers = gmail_client.headers_map(msg)
    subject = headers.get("Subject", "(no subject)")
    from_addr = headers.get("From", "")
    body_text = extract_text_body(msg) or ""
    email_text = f"{subject}\n{body_text}"

    # 1) subject keyword gate
    matches = subject_matches(subject, KEYWORDS)
    if not matches:
        reason = "No policy keyword match in subject"
        deps.log_event({
            "message_id": msg["id"],
            "from_addr": from_addr,
            "subject": subject,
            "decision": "SKIP" if not config.ESCALATE_ON_NOMATCH else "ESCALATE",
            "reason": reason,
            "matched_keywords": []
        })
        # prevent loops: remove IN+UNREAD, mark scanned or escalate
        if config.ESCALATE_ON_NOMATCH:
            deps.escalate(msg["id"])
        else:
            deps.mark_scanned(msg["id"])
        return

    # 2) detect PII in incoming request (we'll redact in reply and escalate after reply)
    pii_req = detect_pii(email_text)

    # 3) run LangGraph
    state = {
        "message_id": msg["id"],
        "from_addr": from_addr,
        "subject": subject,
        "email_text": email_text,
        "matched_keywords": matches,
        "rewrite_count": 0,
        "pii_in_request": pii_req,  # list or []
    }
    GRAPH.invoke(state)

def _build_query() -> str:
    base = f"label:{config.LABEL_IN} is:unread"
    extra = (config.GMAIL_QUERY or "")
    # collapse whitespace to avoid newlines in logs / Gmail API
    q = f"{base} {extra}".strip()
    return " ".join(q.split())


async def _poll_once():
    query = _build_query()
    rprint(f"[dim]Polling with query:[/] {query}")
    msgs = gmail_client.list_messages(SERVICE, q=query)
    if not msgs:
        return
    rprint(f"[bold cyan]Found {len(msgs)} candidate message(s)[/bold cyan]")

    # process in parallel (bounded)
    sem = asyncio.Semaphore(config.MAX_CONCURRENCY)
    async def _run(m):
        async with sem:
            full = gmail_client.get_message(SERVICE, m["id"])
            headers = gmail_client.headers_map(full)
            subj = headers.get("Subject", "(no subject)")
            rprint(f" • [white]{subj}[/]")
            await process_message_with_graph(full)

    await asyncio.gather(*[ _run(m) for m in msgs ])

async def poller():
    global SERVICE, LLM, KEYWORDS, INDEX, LABEL_IDS, GRAPH
    SERVICE = gmail_client.build_service()
    LLM = GeminiClient(api_key=config.GEMINI_API_KEY, per_batch_sleep=1.0)
    KEYWORDS = load_keywords()
    INDEX = build_index(LLM)
    LABEL_IDS = gmail_client.ensure_labels(SERVICE, [config.LABEL_IN, config.LABEL_OUT, config.LABEL_REVIEW, config.LABEL_SCANNED])

    deps.set_runtime(SERVICE, LLM, LABEL_IDS, INDEX)
    GRAPH = build_graph()

    rprint(f"[green]Poller started. Interval:[/green] {config.POLL_INTERVAL}")
    while True:
        try:
            await _poll_once()
        except Exception as e:
            deps.log_event({"event": "ERROR", "detail": str(e)})
            rprint(f"[red]ERROR:[/] {e}")
        await asyncio.sleep(config.POLL_INTERVAL)

@app.on_event("startup")
async def on_start():
    app.state.poller_task = asyncio.create_task(poller())

@app.on_event("shutdown")
async def on_shutdown():
    if app.state.poller_task and not app.state.poller_task.done():
        app.state.poller_task.cancel()
        try:
            await app.state.poller_task
        except asyncio.CancelledError:
            pass

class Health(BaseModel):
    status: str
    poll_interval: int
    label_in: str
    label_out: str
    label_review: str
    label_scanned: str
    query: str

@app.get("/health", response_model=Health)
def health():
    return Health(
        status="ok",
        poll_interval=config.POLL_INTERVAL,
        label_in=config.LABEL_IN,
        label_out=config.LABEL_OUT,
        label_review=config.LABEL_REVIEW,
        label_scanned=config.LABEL_SCANNED,
        query=_build_query(),
    )

@app.get("/poll-now")
async def poll_now():
    await _poll_once()
    return {"ok": True}

@app.get("/keywords")
def get_keywords():
    return KEYWORDS or {}

@app.get("/logs")
def get_logs():
    path = config.LOGS_PATH
    if not os.path.exists(path): return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except:
                continue
    return out[-500:]
