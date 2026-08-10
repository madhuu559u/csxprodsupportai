# CTO Demo Script — NEXUS OpsAI v2 (15 minutes)

> **Before the demo:** `docker compose up -d` in `nexus-opsai`, open http://localhost:8611.
> Header badge should read **AI: OpenAI (gpt-4o-mini)**. Click **Reset demo** once for a
> fresh scenario (ingested real-log sources are preserved). If the AI provider is ever
> unreachable, every panel silently falls back to the built-in deterministic engine —
> the demo cannot fail on stage.

## 1. Positioning (1 min, no screen)
"Production support today is reactive: alert → 40 minutes of grepping → three teams paged →
RCA two days later. NEXUS OpsAI is an intelligence layer *on top of* the tooling we already
own. It detects, explains, predicts, resolves and learns — and everything you'll see is a
running product: React console, PostgreSQL storage, containerized, client-configurable."

## 2. Home (2 min)
- KPI row: active SEV1, predicted incidents, anomalous patterns, ~3,000 log lines in PostgreSQL.
- Service health table: checkout-api critical, web-gateway degraded — "the platform knows the
  dependency graph; nobody typed this in during the incident."
- Telemetry charts: pool pinned at ~100%, latency 2.4s, and hover any chart for point-in-time values.

## 3. Log Intelligence — Use case 1 (2 min)
- Click **AI: Summarize error situation** → OpenAI-generated summary in seconds: dominant
  pattern (68% of errors = pool timeouts), causal chain, next step.
- Cluster table: "160 different raw lines collapse into one masked pattern. And look at the
  `apache-httpd` rows — that's a **real Apache log file we pulled off the internet** and
  ingested through Administration. Zero rules written."

## 4. Predictive Alerts — Use case 2 (2 min)
- Breaches vs Forecasts: "payment-api heap will breach in ~30 minutes at 76% confidence,
  fulfillment queue in ~40 at 98%. This is lead time — nobody's been paged yet.
  Explainable trend models, thresholds tunable per client in Administration."

## 5. Incident Command + AI brief (3 min)
- SEV1 card: severity path bar, correlated signals, blast radius, **change suspect:
  v6.14.2 deployed 26 minutes before onset**.
- **AI incident brief** → sub-minute triage. Expand Evidence — every claim is linked to a
  metric, log cluster or deployment.
- **Recommended runbooks** → execute the tier-2 runbook → **approval modal** (name recorded)
  → steps run → **verification: passed** — pool utilization actually dropped before the
  platform declared success. Back on Home: charts recovering, SEV1 downgraded.

## 6. Runbooks & audit (1 min)
- Tier policy on screen: approval-gated tier 2, auto-heal tier 3, tier 4 refused outright.
- Audit trail: "immutable, in PostgreSQL: who approved, what ran, verification result."

## 7. RCA — Use case 5 (1 min)
- On the incident → **Generate RCA draft**: timeline, root cause, rejected alternatives,
  corrective + preventive actions. "Two-day postmortem becomes one review pass."

## 8. Copilot — Use case 4 (1 min)
- Chips: *What changed?* / *Which runbook?* — grounded in live state, history persisted.

## 9. Administration — the product story (2 min)
This is what makes it a **product we can take to any client**:
- **AI Providers**: paste an OpenAI/Anthropic/Azure key, click **Test** (live call), set
  default. Keys masked, stored in PostgreSQL, automatic failover.
- **Data Sources**: paste logs or fetch a URL — demo it live by re-ingesting the Apache URL.
- **Database Connections**: register a client DB with pool min/max → **Test** shows server
  version, active connections, **pool utilization** — the #1 low-hanging fruit for
  proactive support.
- **Alert Thresholds**: tune per client, no code.

## 10. Close
"Runs anywhere Docker runs. Phase 1 ask: point it read-only at one real service's
Splunk/Prometheus feed and measure detection lead time against the last three incidents."

## Q&A ammunition
- **Wrong AI answers?** Evidence-linked outputs, tiered human-gated remediation, telemetry
  verification, immutable audit, offline fallback.
- **Vendor lock-in?** Three providers configurable at runtime + offline mode; model is data.
- **Security?** Keys masked in UI/API, stored server-side; rotate any key shared over chat;
  secrets-manager integration on the roadmap.
- **Cost?** Pattern mining/prediction run locally; AI calls are per-incident, cents each
  (gpt-4o-mini) with per-provider choice.
