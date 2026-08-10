# NEXUS OpsAI — AI-Native Production Support Platform (v2.2)

A real, deployable implementation of the `ai_production_support_platform_blueprint.html`
vision: one operations console that **detects, explains, predicts, resolves and learns** —
React (Salesforce Lightning-style) console, PostgreSQL persistence (29-table schema),
multi-tenant with login + RBAC, a full application-onboarding wizard, multi-provider AI, client administration, and Docker packaging.

**Multi-tenant out of the box:** ships with two demo customers — Acme Retail (6 apps) and
Globex Financial (4 apps) — and six personas across admin / developer / tester roles.
Sign in from the login page (demo password `demo123`, one-click persona cards); permissions are enforced server-side and
verified by the included [UAT report](UAT_REPORT.md) (25/25 scenarios passed).

## Stack

| Layer | Technology |
|---|---|
| Console | React 18 + Vite, Lightning-style design system (light theme, validated chart palette) |
| API | FastAPI (Python 3.12) with session login (Bearer tokens), header identity for automation, and role permission enforcement |
| Storage | PostgreSQL, 29 tables: sessions, application_patterns, application_sops, tenants, users, roles, applications, application_services, logs, log_sources, metric_samples, metrics_catalog, alerts, predictions_history, incidents, incident_events, incident_comments, runbooks_catalog, runbook_audit, rca_reports, knowledge_articles, ai_providers, ai_usage, db_connections, audit_log, notifications, copilot_history, settings, maintenance_windows |
| AI | Multi-provider hub: **OpenAI**, **Anthropic Claude**, **Azure OpenAI** — configured in Administration, automatic failover, per-call usage metering, deterministic offline engine as final fallback |
| Packaging | Docker multi-stage build + docker-compose (app + postgres) |

## Run — Docker (production shape)

```powershell
cd nexus-opsai
# keys live in .env (or enter them later in Administration > AI Providers)
docker compose up --build
```

Open **http://localhost:8611**.

## Run — local development

```powershell
# needs: Python 3.12+, Node 20+, PostgreSQL running locally
cd nexus-opsai
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python -m uvicorn nexus.main:app --port 8611
```

(Frontend dev loop: `cd frontend && npm run dev` — Vite proxies `/api` to :8611.)


## Application onboarding (collect everything, act on it)

**Administration → Applications → Onboard application** walks a six-step wizard that captures
the complete operating picture of an app: what it does, business impact, SLA, environment,
owner/on-call, telemetry service names, log locations, a bootstrap log sample (paste or URL),
**watch patterns** (regexes the platform scans every ingested log line for — matches are
flagged and feed incidents), backing **databases** (registered with pool min/max for
monitoring), **SOPs** (standard operating procedures that attach to matching incidents and
ground the copilot), and upstream/downstream dependencies. On launch everything is created
in one shot and the platform immediately acts on it — verified in UAT with a "Loyalty
Rewards" app whose `POINTS_LOCK_TIMEOUT` pattern flagged its clusters seconds after onboarding.

## Client administration (the "take it to a client" workflow)

Everything a client configures lives in **Administration** and persists in PostgreSQL:

1. **AI Providers** — paste an OpenAI / Anthropic / Azure OpenAI key, pick the model or
   deployment, click **Test** (makes a real call), set the default. Keys are masked in the
   UI and never returned in full by the API. Failover: default → other enabled providers →
   built-in offline engine.
2. **Data Sources** — ingest logs by pasting raw text or fetching a URL (Splunk/ELK export,
   `kubectl logs`, plain files). The engine parses any common format, masks variables, and
   clusters lines into patterns automatically — verified against real Apache logs from the
   LogHub research corpus (2,000 lines → 6 patterns).
3. **Database Connections** — register the databases behind client applications with pool
   min/max sizing. **Test** makes a live connection, reports server version, active
   connections and pool utilization — connection-pool exhaustion is the #1 low-hanging fruit.
4. **Alert Thresholds** — warn/critical per metric, driving breach detection, incident
   severity and the predictive horizon.

## The five blueprint use cases

| # | Use case | How |
|---|----------|-----|
| 1 | AI Log Analyzer | Template mining + clustering over PostgreSQL-stored logs; AI summary with evidence |
| 2 | Predictive Alerts | Least-squares trend fit → time-to-breach + R² confidence (explainable baselines first) |
| 3 | Automated Runbooks | YAML catalog, tier policy (2 = human approval, 3 = auto-heal, 4 = restricted), telemetry verification, immutable PG audit trail |
| 4 | L1 Copilot | Chat grounded in live incidents/changes/ownership/runbooks; history persists in PG |
| 5 | RCA Generator | Evidence-bounded RCA draft from correlated telemetry + remediation history |

## Demo scenario

Synthetic enterprise telemetry seeds on first boot: checkout-api SEV1 (DB pool exhaustion
after deployment v6.14.2), payment-api heap-leak forecast, fulfillment queue backlog
forecast. **Reset demo** in the header regenerates it. Real ingested sources are kept.

## Security notes

- AI keys are held in PostgreSQL and masked in every API response.
- `.env` is gitignored; `.env.example` documents the variables.
- Rotate any key that has been shared over chat/email before production use.

## Production roadmap (per blueprint phases)

Phase 1: replace the synthetic metrics module with real connectors (Prometheus remote-read,
Splunk/ELK query APIs, ServiceNow) — engines are connector-agnostic. Phase 2: AI triage on
one real service. Phase 3: first three production-safe runbooks using the same tier policy.
Phase 4+: SSO/RBAC, secrets manager for provider keys, HA deployment of the compose stack.
