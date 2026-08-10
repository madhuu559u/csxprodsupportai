"""Use case 1 - AI Log Analyzer.

Turns raw log lines into templated clusters (pattern mining), flags anomalous
error patterns, and prepares evidence for AI summarization. Works on the demo
world's logs and on any log text uploaded through the console.
"""
from __future__ import annotations

import re
from collections import defaultdict

# Masking rules applied in order to derive a stable template from a raw message
_MASKS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b"), "<UUID>"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<IP>"),
    (re.compile(r"\b(ORD|TX|C)[-]?\d+\b"), r"<\1_ID>"),
    (re.compile(r"\b\d+(\.\d+)?(ms|s|%)\b"), "<NUM>\\2"),
    (re.compile(r"\b\d+(\.\d+)?\b"), "<NUM>"),
]

_LINE_RE = re.compile(
    r"^(?P<ts>\S+[ T]\S+)?\s*(?P<level>TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)?"
    r"\s*(?:\[(?P<svc>[\w.-]+)\])?\s*(?P<msg>.*)$"
)


def template_of(message: str) -> str:
    t = message
    for rx, repl in _MASKS:
        t = rx.sub(repl, t)
    return t.strip()


def cluster_logs(logs: list[dict], min_error_count: int = 3) -> list[dict]:
    """Group log entries by (service, level, template)."""
    clusters: dict[tuple, dict] = {}
    for entry in logs:
        key = (entry["service"], entry["level"], template_of(entry["message"]))
        c = clusters.get(key)
        if c is None:
            c = clusters[key] = {
                "service": key[0], "level": key[1], "template": key[2],
                "count": 0, "first_seen": entry["ts"], "last_seen": entry["ts"],
                "example": entry["message"],
            }
        c["count"] += 1
        c["first_seen"] = min(c["first_seen"], entry["ts"])
        c["last_seen"] = max(c["last_seen"], entry["ts"])

    out = sorted(clusters.values(), key=lambda c: (-_sev_rank(c["level"]), -c["count"]))
    for c in out:
        c["anomalous"] = _sev_rank(c["level"]) >= 2 and c["count"] >= min_error_count
    return out


def _sev_rank(level: str) -> int:
    return {"FATAL": 3, "CRITICAL": 3, "ERROR": 2, "WARN": 1, "WARNING": 1}.get(level, 0)


def parse_uploaded(text: str) -> list[dict]:
    """Best-effort parse of arbitrary pasted/uploaded log text into entries."""
    import time
    now = time.time()
    entries = []
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        level = (m.group("level") or "") if m else ""
        if not level:
            # bracketed lowercase levels used by Apache/nginx/syslog styles
            low = line.lower()
            for tag, lvl in (("[error]", "ERROR"), ("[crit]", "FATAL"), ("[alert]", "FATAL"),
                             ("[emerg]", "FATAL"), ("[warn]", "WARN"), ("[warning]", "WARN"),
                             (" error ", "ERROR"), (" warn ", "WARN")):
                if tag in low:
                    level = lvl
                    break
        level = level or "INFO"
        if level == "WARNING":
            level = "WARN"
        if level == "CRITICAL":
            level = "FATAL"
        svc = (m.group("svc") if m else None) or "uploaded"
        msg = (m.group("msg") if m else line) or line
        entries.append({"ts": now - (0.5 * i), "service": svc, "level": level, "message": msg})
    return entries


def error_summary_facts(clusters: list[dict], logs: list[dict]) -> dict:
    """Structured facts fed to the AI (or offline formatter) for summarization."""
    anomalous = [c for c in clusters if c.get("anomalous")]
    total = len(logs)
    errors = sum(1 for l in logs if _sev_rank(l["level"]) >= 2)
    by_service = defaultdict(int)
    for l in logs:
        if _sev_rank(l["level"]) >= 2:
            by_service[l["service"]] += 1
    return {
        "total_lines": total,
        "error_lines": errors,
        "errors_by_service": dict(by_service),
        "top_error_clusters": [
            {"service": c["service"], "template": c["template"], "count": c["count"]}
            for c in anomalous[:8]
        ],
    }
