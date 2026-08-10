# UAT Report — NEXUS OpsAI v2.1

Two simulated customer organizations exercised the product end-to-end through the API and
console, each with three roles (admin / developer / tester). All AI results were produced
live by the configured OpenAI provider; RBAC denials verified server-side.

**Customers under test**

| Customer | Industry | Applications (services) |
|---|---|---|
| Acme Retail | E-commerce | Storefront Edge, Checkout, Payments, Fulfillment, Inventory, Search — 6 apps |
| Globex Financial | Capital markets | Trading Gateway, General Ledger, Risk Engine, Client Notifications — 4 apps |

**Personas:** Priya (Acme admin), Marco (Acme developer), Lena (Acme tester),
Owen (Globex admin), Sara (Globex developer), Tomas (Globex tester).

## Results — 18/18 scenarios passed

| # | Scenario | Persona | Result |
|---|----------|---------|--------|
| 1 | All six personas resolve with correct role + tenant + permissions | all | ✅ |
| 2 | Unknown user rejected (401) | attacker | ✅ |
| 3 | Tenant scoping: Acme sees 6 services, Globex sees 4; incidents scoped | all | ✅ |
| 4 | Admin adds **Azure OpenAI** provider (endpoint + deployment saved, disabled until keys valid) | Priya | ✅ |
| 5 | Admin tunes latency threshold (persists in PG, audited) | Priya | ✅ |
| 6 | Admin registers a **new application** (Billing) and ingests its logs | Priya | ✅ 4 lines → clustered |
| 7 | Developer blocked from admin config (403 with helpful message) | Marco | ✅ |
| 8 | Developer executes tier-2 runbook with approval → verification passed | Marco | ✅ |
| 9 | RCA generated live (OpenAI), persisted to `rca_reports`, auto-published to Knowledge Base | Marco | ✅ 3,355 chars |
| 10 | Incident comment recorded with user identity | Marco | ✅ |
| 11 | Tester denied runbook execution (403) | Lena | ✅ |
| 12 | Tester CAN ingest QA logs and use copilot (live OpenAI) | Lena | ✅ |
| 13 | **Real internet data**: Zookeeper cluster logs (LogHub) ingested via URL — 2,000 lines → 15 patterns | Owen | ✅ |
| 14 | Database connection registered with pool 5–40, live test: connected, 25% pool utilization | Owen | ✅ |
| 15 | Globex incidents visible with change suspect (CHG-2214 feed failover) | Sara | ✅ |
| 16 | trading-feed-reconnect executed (tier 2, approved) → latency verified recovered | Sara | ✅ |
| 17 | Post-remediation breach count drops; tenant notifications generated | Tomas | ✅ |
| 18 | Governance: audit log (9 entries incl. both tenants), AI usage metering, **26-table schema** | Priya | ✅ |

## Findings & dispositions

| Finding | Severity | Disposition |
|---|---|---|
| Table row counts used `pg_stat` estimates and lagged fresh inserts | Low | **Fixed** — real `count(*)` per table |
| Apache/nginx-style lowercase `[error]` tags parsed as INFO | Medium | **Fixed** — bracketed-level detection in the parser |
| Alert thresholds are platform-global: Acme's tighter latency threshold surfaced a Globex incident | Medium | **Documented limitation** — per-tenant thresholds scheduled for the next release; workaround: agree thresholds across tenants or run one deployment per customer |
| Tier-2 approval requires `approve_tier2` permission; testers cannot self-approve | — | Working as designed |
| AI provider failover: with OpenAI down the platform falls to Anthropic (if configured) then offline engine | — | Verified earlier in provider-hub testing |

## Data stored in PostgreSQL at end of UAT (26 tables)

ai_providers, ai_usage, alerts, application_services, applications, audit_log,
copilot_history, db_connections, incident_comments, incident_events, incidents,
knowledge_articles, log_sources, logs (~6,000 lines incl. two internet corpora),
maintenance_windows, metric_samples (3,000 samples), metrics_catalog, notifications,
predictions_history, rca_reports, roles, runbook_audit, runbooks_catalog, settings,
tenants, users.

## Ease-of-use notes incorporated

- Persona switcher in the header (demo SSO stand-in) auto-scopes the console to the
  persona's own customer.
- 403 responses carry actionable text ("Ask a tenant admin…") and surface inline in the UI.
- Tester roles see "view only" states instead of buttons that would fail.
- First-run works with zero configuration (bootstrap admin + offline AI), and every
  configuration action is available in Administration without code or restarts.

**Verdict: approved for demo and pilot deployments.**
