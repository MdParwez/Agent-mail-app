import os
from dotenv import load_dotenv

load_dotenv()

# === Core ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS", "")

# Polling / query
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
GMAIL_QUERY   = os.getenv("GMAIL_QUERY", "").strip()

# Paths
DATA_DIR      = os.getenv("DATA_DIR", "./data")
POLICY_MD     = os.getenv("POLICY_MD", "./data/airlines_policy.md")
KEYWORDS_JSON = os.getenv("KEYWORDS_JSON", "./data/keywords.json")
INDEX_NPZ     = os.getenv("INDEX_NPZ", "./data/policy_index.npz")
INDEX_CHUNKS  = os.getenv("INDEX_CHUNKS", "./data/policy_chunks.json")
LOGS_PATH     = os.getenv("LOGS_PATH", "./data/logs.jsonl")

# === Gmail Labels ===
LABEL_IN      = os.getenv("LABEL_IN", "agent_inbox")
LABEL_OUT     = os.getenv("LABEL_OUT", "processed_by_agent")
LABEL_REVIEW  = os.getenv("LABEL_REVIEW", "needs_human_review")
LABEL_SCANNED = os.getenv("LABEL_SCANNED", "scanned_by_agent")

# === Behavior toggles ===
ESCALATE_ON_NOMATCH = os.getenv("ESCALATE_ON_NOMATCH", "false").lower() == "true"
MAX_CONCURRENCY     = max(1, int(os.getenv("MAX_CONCURRENCY", "4")))
