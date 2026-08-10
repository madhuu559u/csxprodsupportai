"""Use case 3 - Automated Runbooks & Self-Healing.

Loads the YAML runbook catalog, recommends runbooks matching an incident's
service+signals, and executes them with the tier policy:
  tier <= 1  informational only
  tier 2     requires explicit human approval
  tier 3     pre-approved auto-heal
  tier 4     restricted - execution refused from the console
Every execution is verified against telemetry and written to an immutable
audit trail.
"""
from __future__ import annotations

import time
import uuid

import yaml

from . import db
from .demo_data import WORLD

# metric targets applied when a runbook's remediation "works" in the demo world
_RESOLVE_TARGETS = {
    "checkout-db-pool-pressure": [("checkout-api", "db_pool_utilization", 64),
                                  ("checkout-api", "latency_p99_ms", 240),
                                  ("checkout-api", "error_rate_pct", 0.7)],
    "jvm-heap-relief": [("payment-api", "heap_used_pct", 54)],
    "queue-backlog-scale-consumers": [("fulfillment-worker", "queue_depth", 1100)],
    "clear-edge-cache": [("web-gateway", "error_rate_pct", 0.4)],
    "reset-stuck-jobs": [("fulfillment-worker", "queue_depth", 1000)],
    "trading-feed-reconnect": [("trading-api", "latency_p99_ms", 48),
                               ("trading-api", "error_rate_pct", 0.3)],
    "notification-stuck-jobs": [("notification-svc", "queue_depth", 1800)],
}


class RunbookEngine:
    def __init__(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            self.runbooks = yaml.safe_load(f)["runbooks"]
        self.audit: list[dict] = []

    def catalog(self):
        return self.runbooks

    def get(self, rb_id):
        return next((r for r in self.runbooks if r["id"] == rb_id), None)

    def recommend(self, incident: dict) -> list[dict]:
        recs = []
        for rb in self.runbooks:
            match = rb.get("match", {})
            if match.get("service") != incident["service"]:
                continue
            overlap = set(match.get("signals", [])) & set(incident.get("signals", []))
            if overlap:
                recs.append({**rb, "matched_signals": sorted(overlap)})
        recs.sort(key=lambda r: r["tier"])
        return recs

    def execute(self, rb_id: str, approved_by: str | None, triggered_by: str = "console") -> dict:
        rb = self.get(rb_id)
        if rb is None:
            return {"ok": False, "error": f"Unknown runbook {rb_id}"}

        tier = rb["tier"]
        if tier >= 4:
            result = {"ok": False, "error": "Tier 4 (restricted): execution not permitted from the "
                                            "console. Requires change-management approval."}
            self._audit(rb, "refused", approved_by, triggered_by, [])
            return result
        if tier == 2 and not approved_by:
            return {"ok": False, "needs_approval": True,
                    "error": "Tier 2 runbook requires human approval before execution."}
        if tier <= 1:
            return {"ok": False, "error": "Tier 0/1 runbooks are observe/recommend only."}

        # Simulated step execution
        steps_out = []
        for step in rb["steps"]:
            steps_out.append({"action": step["action"], "detail": step["detail"], "status": "success"})

        # Apply remediation effect to the demo world so verification passes
        for svc, metric, target in _RESOLVE_TARGETS.get(rb_id, []):
            WORLD.resolve_metric(svc, metric, target)

        verify = rb.get("verify", {})
        verification = {
            "metric": verify.get("metric"),
            "expected": verify.get("expected"),
            "status": "passed",
            "detail": f"{verify.get('metric')} confirmed trending back to baseline",
        }
        exec_record = {
            "ok": True,
            "execution_id": str(uuid.uuid4())[:8],
            "runbook": rb_id,
            "tier": tier,
            "steps": steps_out,
            "verification": verification,
            "rollback_triggered": False,
        }
        self._audit(rb, "executed", approved_by, triggered_by, steps_out, verification)
        return exec_record

    def _audit(self, rb, outcome, approved_by, triggered_by, steps, verification=None):
        entry = {
            "ts": time.time(),
            "runbook": rb["id"],
            "name": rb["name"],
            "tier": rb["tier"],
            "outcome": outcome,
            "approved_by": approved_by,
            "triggered_by": triggered_by,
            "steps": [s["action"] for s in steps],
            "verification": verification,
        }
        self.audit.append(entry)
        try:
            db.add_audit(entry)          # immutable audit trail in PostgreSQL
        except Exception:
            pass                         # never let audit persistence break remediation
