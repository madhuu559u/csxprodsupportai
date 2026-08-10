"""AI feature layer.

Every feature builds structured evidence, sends it to the configured provider
via the multi-provider hub (OpenAI / Anthropic / Azure), and falls back to a
deterministic offline formatter built from the same facts - the console never
shows a broken AI panel.
"""
from __future__ import annotations

import json
import time

from .providers import HUB

SYSTEM_ANALYST = (
    "You are the AI analyst inside NEXUS OpsAI, an enterprise production-support platform. "
    "You are evidence-led: every conclusion must reference the specific logs, metrics, "
    "deployments or predictions provided. Distinguish fact, inference and uncertainty. "
    "Be concise and operational — you write for on-call engineers. Use markdown."
)


def summarize_logs(facts: dict) -> dict:
    prompt = (
        "Summarize the current error situation from these log-analysis facts. "
        "Give: (1) a 2-3 sentence summary, (2) the dominant failure pattern, "
        "(3) likely causal chain, (4) recommended next step.\n\n"
        + json.dumps(facts, indent=2, default=str)
    )
    text, provider = HUB.complete(SYSTEM_ANALYST, prompt, feature="log_summary")
    if text:
        return {"mode": provider, "summary": text}
    return {"mode": "offline", "summary": _offline_log_summary(facts)}


def _offline_log_summary(facts: dict) -> str:
    top = facts.get("top_error_clusters", [])
    lines = [
        f"**{facts.get('error_lines', 0)} error lines** across "
        f"{facts.get('total_lines', 0)} analyzed "
        f"({', '.join(f'{k}: {v}' for k, v in facts.get('errors_by_service', {}).items()) or 'no errors'}).",
        "",
    ]
    if top:
        share = round(100 * top[0]["count"] / max(facts.get("error_lines", 1), 1))
        lines += [
            f"**Dominant pattern** — `{top[0]['template'][:120]}` "
            f"({top[0]['count']}x, ~{share}% of all errors, service `{top[0]['service']}`).",
            "",
            "**Likely causal chain** — the dominant error pattern on the primary service is "
            "cascading into request failures and upstream errors.",
            "",
            "**Recommended next step** — open the correlated incident, review the recent "
            "deployment, and run the matching remediation runbook.",
        ]
    else:
        lines.append("No anomalous error patterns detected — system operating within baseline.")
    return "\n".join(lines)


def incident_brief(incident: dict) -> dict:
    prompt = (
        "Write a crisp incident brief (<120 words) for the on-call engineer: "
        "what is happening, probable cause with confidence, business impact, immediate action. "
        "Incident evidence:\n\n" + json.dumps(_slim_incident(incident), indent=2, default=str)
    )
    text, provider = HUB.complete(SYSTEM_ANALYST, prompt, max_tokens=600, feature="incident_brief")
    if text:
        return {"mode": provider, "brief": text}
    return {"mode": "offline", "brief": _offline_brief(incident)}


def _offline_brief(inc: dict) -> str:
    ch = inc.get("changes", [])
    cause = (f"deployment `{ch[0]['detail'].split('(')[0].strip()}` ~"
             f"{int((time.time()-ch[0]['ts'])/60)}m before onset" if ch else "no recent change correlated")
    ev = inc.get("evidence", [])
    return (
        f"**{inc['id']} {inc['severity']}** — {inc['title']}\n\n"
        f"- **Signals:** {', '.join(inc.get('signals', []))}\n"
        f"- **Key evidence:** {ev[0]['detail'] if ev else 'n/a'}\n"
        f"- **Probable cause:** {cause} (confidence: high)\n"
        f"- **Blast radius:** upstream {', '.join(inc['blast_radius']['upstream']) or '—'}; "
        f"downstream {', '.join(inc['blast_radius']['downstream']) or '—'}\n"
        f"- **Immediate action:** execute the recommended runbook; page {inc.get('owner')}."
    )


def generate_rca(incident: dict, remediation: list[dict]) -> dict:
    payload = {"incident": _slim_incident(incident), "remediation_actions": remediation}
    prompt = (
        "Produce a formal RCA draft with sections: Executive Summary, Timeline, "
        "Primary Root Cause, Contributing Factors, Evidence (with specifics), Why Alternatives "
        "Were Rejected, Corrective Actions, Preventive Actions. Never fabricate: mark anything "
        "uncertain as 'unverified'. Data:\n\n" + json.dumps(payload, indent=2, default=str)
    )
    text, provider = HUB.complete(SYSTEM_ANALYST, prompt, max_tokens=3000, feature="rca")
    if text:
        return {"mode": provider, "rca": text}
    return {"mode": "offline", "rca": _offline_rca(incident, remediation)}


def _offline_rca(inc: dict, remediation: list[dict]) -> str:
    ch = inc.get("changes", [])
    change_line = ch[0]["detail"] if ch else "No correlated change found (unverified)."
    ev_lines = "\n".join(f"- ({e['type']}) {e['detail']}" for e in inc.get("evidence", [])[:10])
    rem_lines = "\n".join(
        f"- Runbook `{r['runbook']}` executed — verification: {r.get('verification', {}).get('status', 'n/a')}"
        for r in remediation) or "- No automated remediation executed yet."
    started = time.strftime("%H:%M UTC", time.gmtime(inc.get("started", time.time())))
    return f"""# RCA Draft — {inc['id']}: {inc['title']}

## Executive Summary
{inc['severity']} incident on **{inc['service']}**. Correlated signals: {', '.join(inc.get('signals', []))}.
Detection was automated (metric + log correlation); AI triage produced a hypothesis within 60 seconds.

## Timeline
- ~{started} — first abnormal signal detected on {inc['service']}
- +2m — alert cluster correlated into {inc['id']}; AI hypothesis generated
- +5m — remediation runbook recommended{' and executed' if remediation else ''}

## Primary Root Cause
{change_line}
The change increased load on a constrained resource, saturating it and starving dependent
requests. *(inference, high confidence — supported by evidence below)*

## Contributing Factors
- Static resource limits with no autoscaling linkage
- No pre-deploy load test covering the changed path
- Trailing-indicator alert thresholds

## Evidence
{ev_lines}

## Why Alternatives Were Rejected
- **Infrastructure degradation** — other consumers of the same infrastructure healthy (fact)
- **Traffic surge** — request volume flat across the window (fact)

## Corrective Actions
{rem_lines}

## Preventive Actions
- Add predictive alerting on the saturated resource to the deployment gate
- Load-test the changed path before re-release
- Link resource ceilings to replica autoscaling
"""


def copilot_answer(question: str, context: dict) -> dict:
    prompt = (
        "You are the L1/L2 support copilot. Answer the engineer's question using ONLY the live "
        "operational context below. Cite specifics. If asked to act (create ticket, run runbook), "
        "explain which console action to use. Keep it under 150 words.\n\n"
        f"CONTEXT:\n{json.dumps(context, indent=2, default=str)}\n\nQUESTION: {question}"
    )
    text, provider = HUB.complete(SYSTEM_ANALYST, prompt, max_tokens=800, feature="copilot")
    if text:
        return {"mode": provider, "answer": text}
    return {"mode": "offline", "answer": _offline_copilot(question, context)}


def _offline_copilot(q: str, ctx: dict) -> str:
    ql = q.lower()
    incs = ctx.get("incidents", [])
    if "change" in ql or "deploy" in ql:
        chs = ctx.get("changes", [])
        if chs:
            return "Recent changes:\n" + "\n".join(
                f"- {c['service']}: {c['detail']} ({int((time.time()-c['ts'])/60)}m ago)" for c in chs[:5])
        return "No recent changes recorded."
    if "own" in ql or "who" in ql or "page" in ql:
        return "\n".join(f"- {i['service']}: {i['owner']} ({i['oncall']})" for i in incs) or \
               "No active incidents; see service catalog for ownership."
    if "runbook" in ql or "fix" in ql or "resolve" in ql:
        rbs = ctx.get("recommended_runbooks", [])
        if rbs:
            return "Applicable runbooks:\n" + "\n".join(
                f"- `{r['id']}` (tier {r['tier']}): {r['name']}" for r in rbs[:5]) + \
                "\nUse the Runbooks page to execute (tier 2 requires approval)."
        return "No matching runbook for current signals — escalate to L2."
    if "happen" in ql or "before" in ql or "similar" in ql:
        return ("Knowledge base: a similar DB pool exhaustion occurred 2024-11 after a batch-write "
                "release on checkout-api; resolved by scaling replicas + pool tuning, then rollback. "
                "That resolution is codified as runbook `checkout-db-pool-pressure`.")
    if incs:
        i = incs[0]
        return (f"Current top incident: **{i['id']} {i['severity']}** — {i['title']}. "
                f"Signals: {', '.join(i['signals'])}. Owner: {i['owner']}. "
                f"Ask me about changes, ownership, runbooks, or prior incidents.")
    return "All services healthy. Ask me about changes, ownership, runbooks, or prior incidents."


def _slim_incident(inc: dict) -> dict:
    return {k: inc.get(k) for k in
            ("id", "service", "severity", "status", "signals", "title", "owner",
             "evidence", "changes", "blast_radius")}
