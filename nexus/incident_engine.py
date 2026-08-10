"""Incident correlation.

Collects signals from three sources - metric breaches, predictive alerts, and
anomalous log clusters - deduplicates, groups them per service inside a time
window, and materializes incidents with severity, blast radius (from topology)
and correlated recent changes.
"""
from __future__ import annotations

import time

from .demo_data import SERVICE_META, TOPOLOGY

# metric -> canonical signal name used by runbook matching
SIGNAL_OF_METRIC = {
    "db_pool_utilization": "db_pool_exhaustion",
    "heap_used_pct": "jvm_memory_leak",
    "latency_p99_ms": "latency_spike",
    "queue_depth": "queue_backlog",
    "error_rate_pct": "error_spike",
}


def build_incidents(breaches: list[dict], preds: list[dict], clusters: list[dict],
                    changes: list[dict], window_min: int = 30) -> list[dict]:
    now = time.time()
    per_service: dict[str, dict] = {}

    def bucket(service):
        if service not in per_service:
            per_service[service] = {"signals": [], "evidence": [], "predictive_only": True}
        return per_service[service]

    for b in breaches:
        s = bucket(b["service"])
        s["predictive_only"] = False
        s["signals"].append(SIGNAL_OF_METRIC.get(b["metric"], b["metric"]))
        s["evidence"].append({
            "type": "metric", "severity": b["level"],
            "detail": f"{b['metric']} = {b['value']} (threshold {b['threshold']})",
        })

    for p in preds:
        s = bucket(p["service"])
        s["signals"].append(SIGNAL_OF_METRIC.get(p["metric"], p["metric"]))
        s["evidence"].append({
            "type": "prediction", "severity": "warn",
            "detail": f"{p['title']} forecast in ~{p['eta_minutes']}m "
                      f"(now {p['current']}{p['unit']}, confidence {p['confidence']})",
        })

    for c in clusters:
        if not c.get("anomalous"):
            continue
        if c["service"] not in per_service and c["level"] not in ("ERROR", "FATAL"):
            continue
        s = bucket(c["service"])
        if c["level"] in ("ERROR", "FATAL"):
            s["predictive_only"] = False
        s["evidence"].append({
            "type": "log", "severity": "critical" if c["level"] == "FATAL" else "error",
            "detail": f"{c['count']}x {c['template'][:140]}",
        })

    incidents = []
    idx = 1
    for service, data in per_service.items():
        crit_metrics = [e for e in data["evidence"] if e["type"] == "metric" and e["severity"] == "critical"]
        if data["predictive_only"]:
            sev = "SEV3"
        elif crit_metrics and SERVICE_META.get(service, {}).get("criticality") == "critical":
            sev = "SEV1"
        elif crit_metrics:
            sev = "SEV2"
        else:
            sev = "SEV3"

        related_changes = [
            ch for ch in changes
            if ch["service"] == service and now - ch["ts"] <= max(window_min, 60) * 60
        ]
        signals = sorted(set(data["signals"]))
        incidents.append({
            "id": f"INC-{1000 + idx}",
            "service": service,
            "severity": sev,
            "status": "predicted" if data["predictive_only"] else "active",
            "signals": signals,
            "title": _title(service, signals, data["predictive_only"]),
            "owner": SERVICE_META.get(service, {}).get("owner", "unknown"),
            "oncall": SERVICE_META.get(service, {}).get("oncall", ""),
            "evidence": data["evidence"],
            "changes": related_changes,
            "blast_radius": _blast_radius(service),
            "started": now - window_min * 60 if not data["predictive_only"] else now,
        })
        idx += 1

    order = {"SEV1": 0, "SEV2": 1, "SEV3": 2}
    incidents.sort(key=lambda i: order.get(i["severity"], 9))
    return incidents


def _title(service, signals, predictive):
    names = {
        "db_pool_exhaustion": "DB connection pool exhaustion",
        "jvm_memory_leak": "JVM heap pressure",
        "latency_spike": "latency spike",
        "queue_backlog": "queue backlog",
        "error_spike": "elevated error rate",
    }
    main = names.get(signals[0], signals[0]) if signals else "anomalous error pattern"
    prefix = "Predicted: " if predictive else ""
    return f"{prefix}{service} — {main}" + (f" (+{len(signals)-1} correlated signals)" if len(signals) > 1 else "")


def _blast_radius(service):
    downstream = TOPOLOGY.get(service, [])
    upstream = [s for s, deps in TOPOLOGY.items() if service in deps]
    return {"upstream": upstream, "downstream": downstream}
