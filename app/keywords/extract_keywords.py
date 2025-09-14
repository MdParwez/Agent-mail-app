import re
import json
import pathlib
import collections
from typing import List

# Simple, safe STOP list (no triple quotes)
STOP = set(
    (
        "a an the and or of to for from in on with without at by is are was were be been will "
        "can could should would may might do does did not no yes as if when then than so such "
        "this that these those i you he she it we they him her them your our their us etc eg "
        "ie per via inc ltd co com www http https"
    ).split()
)


def split_chunks(md_text: str) -> List[str]:
    """Split on headings and blank lines to get coarse chunks."""
    parts = re.split(r"\n(?=#+\s)|\n{2,}", md_text)
    parts = [p.strip() for p in parts if p.strip()]
    return parts


def normalize_word(w: str) -> str:
    return re.sub(r"[^a-z0-9\-]+", "", w.lower())


def extract_phrases(lines: List[str]) -> List[str]:
    """Pull 2–5 word phrases mostly from headings/Q lines."""
    phrases = []
    for ln in lines:
        if ln.startswith("#") or "?" in ln or ln.strip().endswith(":"):
            t = re.sub(r"^[\-\*\d\.\)\(]+\s*", "", ln).strip()
            tokens = [normalize_word(x) for x in re.findall(r"[A-Za-z0-9\-']+", t)]
            tokens = [x for x in tokens if x and x not in STOP and len(x) > 2]
            for n in (2, 3, 4, 5):
                for i in range(0, len(tokens) - n + 1):
                    phrases.append(" ".join(tokens[i : i + n]))
    c = collections.Counter(phrases)
    out = [p for p, _ in c.most_common(200)]
    return out


def extract_unigrams(text: str) -> List[str]:
    tokens = [normalize_word(x) for x in re.findall(r"[A-Za-z0-9\-']+", text)]
    tokens = [t for t in tokens if t and t not in STOP and len(t) > 2]
    c = collections.Counter(tokens)
    kept = [w for w, f in c.items() if f >= 3 or len(w) >= 8]
    kept = sorted(set(kept), key=lambda x: (-len(x), x))
    return kept[:300]


def build_keywords(md_path: str, out_json: str):
    text = pathlib.Path(md_path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    phrases = extract_phrases(lines)
    unigrams = extract_unigrams(text)

    # Force-include some domain terms if present in policies
    MUST = [
        "invoice",
        "rebook",
        "rebooking",
        "cancellation",
        "refund",
        "credit card",
        "3-d secure",
        "economy light",
        "economy classic",
        "economy flex",
        "group booking",
        "additional baggage",
        "upgrade",
        "seat reservation",
        "booking reference",
        "ticket number",
        "fare",
        "booking class",
        "powerpay",
        "id scan",
        "pay per invoice",
    ]
    for m in MUST:
        mnorm = m.lower()
        if " " in mnorm:
            if mnorm not in phrases:
                phrases.append(mnorm)
        else:
            if mnorm not in unigrams:
                unigrams.append(mnorm)

    data = {
        "phrases": sorted(set(phrases))[:300],
        "unigrams": sorted(set(unigrams))[:300],
    }
    pathlib.Path(out_json).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


if __name__ == "__main__":
    import sys

    md = sys.argv[1] if len(sys.argv) > 1 else "./data/airlines_policy.md"
    out = sys.argv[2] if len(sys.argv) > 2 else "./data/keywords.json"
    data = build_keywords(md, out)
    print(
        f"Keywords written to {out}. phrases={len(data['phrases'])}, unigrams={len(data['unigrams'])}"
    )
