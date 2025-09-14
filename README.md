
# Email Agent (Gemini + Subject Keywords)

**What it does (summary):**
- Polls Gmail inbox for `testaionos@gmail.com`
- Extracts keywords from your policy file (`data/airlines_policy.md`) and **matches them against email subjects**.
- If subject contains any policy keywords → **replies** (Gemini) using RAG on your policy.
- If no match → **leaves the mail untouched** and **logs SKIP + reason**.
- Beautiful **Streamlit Logs UI** in `app/ui/logs_app.py`.

## 0) One-time setup

1. Put your `credentials.json` (Gmail OAuth) next to `app/email/gmail_client.py`.
2. Copy `.env.example` → `.env` and set your `GEMINI_API_KEY` (free) and ensure `GMAIL_ADDRESS` is correct.
3. Ensure your policy lives at `data/airlines_policy.md` (already copied).

## 1) Install & bootstrap
```bash
bash scripts/bootstrap.sh
```

This installs deps and **builds keywords** into `data/keywords.json`.

## 2) Run the agent (server + background poller)
```bash
uvicorn app.main:app --reload --port 8000
```
- On startup the agent creates a **background task** that polls Gmail every `POLL_INTERVAL` seconds (default 60).
- It only replies if **subject keyword match** succeeds.

## 3) Start the Logs UI
```bash
streamlit run app/ui/logs_app.py --server.port 8501
```
- Live metrics, search, auto-refresh.

## Endpoints
- `GET /health` — status.
- `GET /keywords` — the active keyword list.
- `GET /logs` — last 500 events.

## Notes
- Generation: `gemini-2.5-flash` (fast; free tier) for drafting.
- Embeddings: `gemini-embedding-001` (RAG; 768-dim) for index/query.
- Continuous poller uses Gmail search: `to:YOUR_ADDRESS is:unread` (configurable via `.env`).
