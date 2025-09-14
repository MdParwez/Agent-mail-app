from __future__ import annotations
import base64
import os
import re
from typing import Dict, Any, List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Gmail modify scope (read/send/labels)
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _paths() -> Dict[str, str]:
    """
    Resolve credentials.json and token.json inside this folder (app/email).
    """
    here = os.path.dirname(__file__)
    return {
        "token": os.path.join(here, "token.json"),
        "creds": os.path.join(here, "credentials.json"),
    }


def _creds(
    token_path: Optional[str] = None,
    creds_path: Optional[str] = None,
) -> Credentials:
    """
    Load or create OAuth credentials. First run will open a browser for consent.
    token.json is persisted for silent auth in subsequent runs.
    """
    p = _paths()
    token_path = token_path or p["token"]
    creds_path = creds_path or p["creds"]

    creds: Optional[Credentials] = None

    # Load existing token if present
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # If no valid creds, either refresh or do a new local-server flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"credentials.json not found at: {creds_path}\n"
                    "Download the OAuth client (Desktop app) JSON from Google Cloud → "
                    "APIs & Services → Credentials, and place it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            # Opens a local browser; after consent, writes token.json
            creds = flow.run_local_server(port=0)
        # Save token for next time
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def build_service(creds: Optional[Credentials] = None):
    """
    Create a Gmail API service client.
    """
    if creds is None:
        creds = _creds()
    # Disable discovery cache to avoid permission issues on some systems
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_messages(
    service, user_id: str = "me", q: Optional[str] = None, label_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    List messages matching query/labels. Automatically handles paging.
    """
    msgs: List[Dict[str, Any]] = []
    req = service.users().messages().list(userId=user_id, q=q, labelIds=label_ids or [])
    while req is not None:
        resp = req.execute()
        for m in resp.get("messages", []):
            msgs.append(m)
        req = service.users().messages().list_next(previous_request=req, previous_response=resp)
    return msgs


def get_message(service, msg_id: str, user_id: str = "me") -> Dict[str, Any]:
    """
    Fetch a message in 'full' format (includes headers + MIME parts).
    """
    return service.users().messages().get(userId=user_id, id=msg_id, format="full").execute()


def send_reply(
    service, to_addr: str, subject: str, body: str, user_id: str = "me"
) -> Dict[str, Any]:
    """
    Send a simple plaintext reply with minimal MIME.
    """
    msg = f"To: {to_addr}\r\nSubject: {subject}\r\n\r\n{body}"
    raw = base64.urlsafe_b64encode(msg.encode("utf-8")).decode("utf-8")
    return service.users().messages().send(userId=user_id, body={"raw": raw}).execute()


def modify_labels(
    service,
    msg_id: str,
    add: Optional[List[str]] = None,
    remove: Optional[List[str]] = None,
    user_id: str = "me",
) -> Dict[str, Any]:
    """
    Add/remove labels by ID (or name, if you've looked up IDs).
    """
    body = {"addLabelIds": add or [], "removeLabelIds": remove or []}
    return service.users().messages().modify(userId=user_id, id=msg_id, body=body).execute()


# -----------------------
# Helpers you’ll likely use
# -----------------------

def list_labels(service, user_id: str = "me") -> List[Dict[str, Any]]:
    """
    Return all labels (name + id).
    """
    return service.users().labels().list(userId=user_id).execute().get("labels", [])


def ensure_labels(service, names: List[str], user_id: str = "me") -> Dict[str, str]:
    """
    Ensure labels exist; returns {label_name: label_id}.
    Creates missing labels with visible settings.
    """
    existing = {lab["name"]: lab["id"] for lab in list_labels(service, user_id)}
    out: Dict[str, str] = {}
    for name in names:
        if name in existing:
            out[name] = existing[name]
        else:
            created = service.users().labels().create(
                userId=user_id,
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            ).execute()
            out[name] = created["id"]
    return out


def headers_map(msg: Dict[str, Any]) -> Dict[str, str]:
    """
    Convert Gmail headers array to {name:value} dict.
    """
    headers = msg.get("payload", {}).get("headers", []) or []
    return {h.get("name", ""): h.get("value", "") for h in headers}


def _walk_mime_for_text(part: Dict[str, Any]) -> Optional[str]:
    """
    Depth-first walk to return text/plain; fallback to stripped text/html.
    """
    mime = part.get("mimeType", "")
    body = part.get("body", {}) or {}
    data = body.get("data")

    # If multipart, iterate its parts
    if mime.startswith("multipart/"):
        for p in part.get("parts", []) or []:
            t = _walk_mime_for_text(p)
            if t:
                return t
        return None

    # Leaf: try text/plain, else text/html
    if not data:
        return None

    try:
        raw = base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    except Exception:
        return None

    if mime == "text/plain":
        return raw

    if mime == "text/html":
        # remove HTML tags to get plain text
        return re.sub(r"<[^>]+>", " ", raw)

    return None


def extract_text_body(msg: Dict[str, Any]) -> str:
    """
    Extract human-readable body text from Gmail message payload.
    Prefers text/plain; falls back to stripped text/html; last resort: snippet.
    """
    payload = msg.get("payload", {}) or {}
    text = _walk_mime_for_text(payload)
    return text or msg.get("snippet", "")
