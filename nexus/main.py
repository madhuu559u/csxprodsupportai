"""NEXUS OpsAI v2 — application entrypoint.

PostgreSQL-backed, multi-provider AI, client-configurable administration.
Run:  uvicorn nexus.main:app --port 8611     (or docker compose up)
"""
from __future__ import annotations

import os
import pathlib
import time
import urllib.request
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fastapi import Depends, Header, HTTPException

from . import ai_gateway, db, incident_engine, log_engine, metrics_engine
from .demo_data import APPLICATIONS, SERVICE_META, TENANTS, TOPOLOGY, WORLD
from .metrics_engine import FRIENDLY
from .providers import DEFAULT_MODELS, HUB
from .runbook_engine import RunbookEngine

ROOT = pathlib.Path(__file__).resolve().parent.parent

# load .env (no external dependency)
_envfile = ROOT / ".env"
if _envfile.exists():
    for _line in _envfile.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

with open(ROOT / "config" / "settings.yaml", "r", encoding="utf-8") as f:
    FILE_CONFIG = yaml.safe_load(f)

RUNBOOKS = RunbookEngine(str(ROOT / "config" / "runbooks.yaml"))
REMEDIATIONS: dict[str, list[dict]] = {}


# ---------------------------------------------------------------- startup
def _seed():
    """First-boot seeding: thresholds, demo log source, env-provided AI keys."""
    if db.get_setting("thresholds") is None:
        db.set_setting("thresholds", FILE_CONFIG["thresholds"])
    if db.get_setting("prediction") is None:
        db.set_setting("prediction", FILE_CONFIG["prediction"])

    # env-provided provider keys (e.g. from .env / container secrets)
    if os.environ.get("OPENAI_API_KEY") and not (db.get_provider("openai") or {}).get("api_key"):
        db.upsert_provider("openai", api_key=os.environ["OPENAI_API_KEY"],
                           model=DEFAULT_MODELS["openai"], enabled=True, is_default=True)
    if os.environ.get("ANTHROPIC_API_KEY") and not (db.get_provider("anthropic") or {}).get("api_key"):
        db.upsert_provider("anthropic", api_key=os.environ["ANTHROPIC_API_KEY"],
                           model=DEFAULT_MODELS["anthropic"], enabled=True)

    # ---- identity: tenants, roles, users ----
    for t in TENANTS:
        db.upsert_tenant(t["slug"], t["name"], t["industry"])
    db.upsert_role("admin", "Full platform administration",
                   {"admin_config": True, "execute_runbooks": True, "approve_tier2": True,
                    "ingest": True, "ai_actions": True})
    db.upsert_role("developer", "Investigate and remediate incidents",
                   {"admin_config": False, "execute_runbooks": True, "approve_tier2": True,
                    "ingest": True, "ai_actions": True})
    db.upsert_role("tester", "Validate platform behavior; read + ingest only",
                   {"admin_config": False, "execute_runbooks": False, "approve_tier2": False,
                    "ingest": True, "ai_actions": True})
    for email, name, tenant, role in [
        ("priya.admin@acme.com", "Priya Sharma", "acme", "admin"),
        ("dev.marco@acme.com", "Marco Diaz", "acme", "developer"),
        ("qa.lena@acme.com", "Lena Fischer", "acme", "tester"),
        ("owen.admin@globex.com", "Owen Wright", "globex", "admin"),
        ("dev.sara@globex.com", "Sara Chen", "globex", "developer"),
        ("qa.tomas@globex.com", "Tomas Novak", "globex", "tester"),
    ]:
        db.upsert_user(email, name, tenant, role)
    # demo credentials: password 'demo123' for every persona (set once)
    for u in db.list_users():
        with db.Cur() as c:
            c.execute("SELECT password_hash FROM users WHERE email=%s", (u["email"],))
            if not c.fetchone()["password_hash"]:
                db.set_password(u["email"], "demo123")

    # ---- application catalog ----
    for tenant, name, owner, oncall, crit, desc, services in APPLICATIONS:
        db.upsert_application(tenant, name, owner, oncall, crit, desc, services)

    # ---- metrics catalog + runbook catalog + knowledge seed ----
    db.upsert_metrics_catalog(FRIENDLY)
    db.sync_runbooks_catalog(RUNBOOKS.catalog())
    if not db.list_knowledge():
        db.add_knowledge("acme", "KB: DB pool exhaustion after batch-write releases",
                         ["postgres", "hikaricp", "checkout"],
                         "2024-11 incident: parallelized writes saturated HikariCP pool (50 max). "
                         "Fix: scale replicas + temporary pool raise, then rollback. Codified as "
                         "runbook checkout-db-pool-pressure.", "postmortem")
        db.add_knowledge("globex", "KB: Stale-price rejections during feed failover",
                         ["market-data", "trading"],
                         "DR-site market data feed adds 4-5s tick latency; order flow must be "
                         "paused or feed reconnected to primary. Codified as runbook "
                         "trading-feed-reconnect.", "postmortem")

    # ---- seed watch patterns + SOPs for the demo apps ----
    if not db.list_patterns():
        apps = {a["name"]: a["id"] for a in db.list_applications()}
        if "Checkout" in apps:
            db.add_pattern(apps["Checkout"], "DB pool timeout", "timeout acquiring connection",
                           "critical", "HikariCP pool starvation — known failure mode after "
                           "write-heavy releases")
            db.add_sop(apps["Checkout"], "SOP: Checkout DB pool exhaustion",
                       "SQLException 'timeout acquiring connection' storm / pool at 100%",
                       "1. Confirm db_pool_utilization > 92% on the Checkout dashboard.\n"
                       "2. Execute runbook checkout-db-pool-pressure (tier 2 — needs approval).\n"
                       "3. Verify pool utilization drops >= 25% within 5 minutes.\n"
                       "4. If not recovered in 10 minutes, escalate to change management for "
                       "release rollback (tier 4).")
        if "Trading Gateway" in apps:
            db.add_pattern(apps["Trading Gateway"], "Stale price rejection", "stale price",
                           "error", "Orders rejected on stale quotes — market-data feed latency")
            db.add_sop(apps["Trading Gateway"], "SOP: Market-data feed degradation",
                       "MarketDataTimeout errors / stale-price order rejections",
                       "1. Check feed session heartbeats per venue.\n"
                       "2. Execute runbook trading-feed-reconnect (tier 2 — needs approval).\n"
                       "3. Verify p99 latency back under 200ms within 5 minutes.\n"
                       "4. Notify the trading desk if order flow is paused for more than 5 minutes.")

    # ---- demo telemetry -> postgres ----
    if db.logs_count() == 0:
        sid = db.create_source("Demo scenario (synthetic enterprise telemetry)", "demo")
        db.insert_logs(WORLD.logs, sid)
    db.store_metric_samples(WORLD.metrics)


# ---------------------------------------------------------------- RBAC / auth
def current_user(authorization: str | None = Header(default=None),
                 x_user_email: str | None = Header(default=None)):
    """Resolve the acting user.

    Order: Bearer session token (console login) -> X-User-Email header (API/automation)
    -> platform bootstrap admin (first-run/scripting). Unknown identity -> 401.
    """
    if authorization and authorization.lower().startswith("bearer "):
        u = db.session_user(authorization.split(" ", 1)[1])
        if not u:
            raise HTTPException(401, "Session expired or invalid — sign in again.")
        return u
    if x_user_email:
        u = db.get_user(x_user_email)
        if not u:
            raise HTTPException(401, f"Unknown or inactive user: {x_user_email}")
        return u
    return {"email": "platform@nexus.local", "display_name": "Platform Bootstrap",
            "tenant": None, "tenant_name": "Platform", "role": "admin",
            "permissions": {"admin_config": True, "execute_runbooks": True,
                            "approve_tier2": True, "ingest": True, "ai_actions": True}}


def require(user, perm):
    if not user["permissions"].get(perm):
        raise HTTPException(403, f"Role '{user['role']}' lacks permission '{perm}'. "
                                 f"Ask a tenant admin to perform this action.")


@asynccontextmanager
async def lifespan(app):
    db.init_pool()
    db.init_schema()
    _seed()
    yield


app = FastAPI(title="NEXUS OpsAI", lifespan=lifespan)


# ---------------------------------------------------------------- helpers
def _thresholds():
    return db.get_setting("thresholds", FILE_CONFIG["thresholds"])


def _pred_cfg():
    return db.get_setting("prediction", FILE_CONFIG["prediction"])


def _all_logs():
    return db.fetch_logs(limit=25000)


def _clusters(logs=None):
    logs = logs if logs is not None else _all_logs()
    clusters = log_engine.cluster_logs(logs, FILE_CONFIG["log_analysis"]["error_cluster_min_count"])
    # Overlay client-configured watch patterns (from application onboarding):
    # a matching cluster is flagged and labeled - configuration acts on live telemetry.
    import re as _re
    try:
        patterns = db.list_patterns()
    except Exception:
        patterns = []
    for c in clusters:
        for p in patterns:
            if p["services"] and c["service"] not in p["services"]:
                continue
            hit = False
            try:
                hit = bool(_re.search(p["pattern"], c["template"], _re.I))
            except _re.error:
                hit = p["pattern"].lower() in c["template"].lower()
            if hit:
                c["matched_pattern"] = p["name"]
                c["pattern_severity"] = p["severity"]
                if p["severity"] in ("error", "critical"):
                    c["anomalous"] = True
                break
    return clusters


_NOTIFIED: set[str] = set()


def _incidents(tenant: str | None = None):
    pc = _pred_cfg()
    th = _thresholds()
    breaches = metrics_engine.current_breaches(WORLD.metrics, th)
    preds = metrics_engine.predictions(WORLD.metrics, th, pc["lookback_points"],
                                       pc["horizon_minutes"], pc["min_confidence"])
    incs = incident_engine.build_incidents(breaches, preds, _clusters(), WORLD.changes,
                                           FILE_CONFIG["correlation"]["window_minutes"])
    try:
        db.upsert_incidents(incs)
        for i in incs:
            key = f"{i['service']}|{i['severity']}|{i['status']}"
            if key not in _NOTIFIED and i["status"] == "active":
                _NOTIFIED.add(key)
                t = SERVICE_META.get(i["service"], {}).get("tenant")
                if t:
                    db.add_notification(t, i["severity"], f"{i['id']}: {i['title']}",
                                        f"Signals: {', '.join(i['signals'])}. Owner: {i['owner']}.")
                db.add_incident_event(i["id"], "detected",
                                      f"{i['severity']} correlated from {len(i['evidence'])} evidence items")
    except Exception:
        pass
    if tenant:
        incs = [i for i in incs if SERVICE_META.get(i["service"], {}).get("tenant") == tenant]
    return incs


def _find_incident(inc_id: str):
    return next((i for i in _incidents() if i["id"] == inc_id), None)


# ---------------------------------------------------------------- authentication
class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginBody):
    if not db.verify_login(body.email.strip().lower(), body.password):
        db.log_audit(body.email, "login_failed", "auth", {})
        raise HTTPException(401, "Invalid email or password.")
    token = db.create_session(body.email.strip().lower())
    user = db.get_user(body.email.strip().lower())
    db.log_audit(user["email"], "login", "auth", {"role": user["role"]})
    return {"token": token, "user": user}


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        db.delete_session(authorization.split(" ", 1)[1])
    return {"ok": True}


@app.get("/api/auth/demo-credentials")
def demo_credentials():
    """Demo persona directory for the login screen (password: demo123)."""
    return {"password_hint": "demo123",
            "personas": [{"email": u["email"], "name": u["display_name"],
                          "role": u["role"], "tenant": u["tenant_name"]}
                         for u in db.list_users()]}


# ---------------------------------------------------------------- identity
@app.get("/api/whoami")
def whoami(user=Depends(current_user)):
    return user


@app.get("/api/users")
def users_public():
    """User directory for the persona switcher (demo SSO stand-in)."""
    return {"users": db.list_users(), "tenants": db.list_tenants()}


# ---------------------------------------------------------------- overview
@app.get("/api/overview")
def overview(tenant: str | None = None):
    incs = _incidents(tenant)
    clusters = _clusters()
    st = HUB.status()
    services = {s: m for s, m in SERVICE_META.items() if not tenant or m["tenant"] == tenant}
    return {
        "platform": "NEXUS OpsAI",
        "ai": st,
        "tenant": tenant,
        "services": [{"name": s, **services[s], "health": _service_health(s, incs)}
                     for s in services],
        "kpis": {
            "active_incidents": sum(1 for i in incs if i["status"] == "active"),
            "predicted_incidents": sum(1 for i in incs if i["status"] == "predicted"),
            "error_clusters": sum(1 for c in clusters if c.get("anomalous")
                                  and (not tenant or SERVICE_META.get(c["service"], {}).get("tenant") == tenant)),
            "log_lines_analyzed": db.logs_count(),
            "runbooks_available": len(RUNBOOKS.catalog()),
            "automations_run": db.audit_count(),
        },
        "topology": TOPOLOGY,
    }


def _service_health(service, incidents):
    for i in incidents:
        if i["service"] == service:
            if i["severity"] == "SEV1":
                return "critical"
            if i["status"] == "active":
                return "degraded"
            return "at-risk"
    return "healthy"


# ---------------------------------------------------------------- metrics / predictions
@app.get("/api/metrics")
def metrics(tenant: str | None = None):
    mm = {s: v for s, v in WORLD.metrics.items()
          if not tenant or SERVICE_META.get(s, {}).get("tenant") == tenant}
    return {"metrics": mm, "thresholds": _thresholds()}


@app.get("/api/predictions")
def predictions(tenant: str | None = None):
    pc = _pred_cfg()
    th = _thresholds()
    breaches = metrics_engine.current_breaches(WORLD.metrics, th)
    preds = metrics_engine.predictions(WORLD.metrics, th, pc["lookback_points"],
                                       pc["horizon_minutes"], pc["min_confidence"])
    try:
        db.record_alerts(breaches, preds)
    except Exception:
        pass
    if tenant:
        breaches = [b for b in breaches if SERVICE_META.get(b["service"], {}).get("tenant") == tenant]
        preds = [p for p in preds if SERVICE_META.get(p["service"], {}).get("tenant") == tenant]
    return {"breaches": breaches, "predictions": preds}


# ---------------------------------------------------------------- logs
@app.get("/api/logs/clusters")
def log_clusters():
    return {"clusters": _clusters()[:50]}


@app.post("/api/logs/analyze")
def analyze_logs():
    logs = _all_logs()
    clusters = _clusters(logs)
    facts = log_engine.error_summary_facts(clusters, logs)
    return ai_gateway.summarize_logs(facts)


# ---------------------------------------------------------------- incidents
@app.get("/api/incidents")
def incidents(tenant: str | None = None):
    return {"incidents": _incidents(tenant)}


@app.get("/api/incidents/{inc_id}")
def incident_detail(inc_id: str):
    inc = _find_incident(inc_id)
    if not inc:
        return JSONResponse({"error": "not found"}, status_code=404)
    inc["recommended_runbooks"] = [
        {"id": r["id"], "name": r["name"], "tier": r["tier"], "matched_signals": r["matched_signals"]}
        for r in RUNBOOKS.recommend(inc)]
    inc["sops"] = [{"id": s["id"], "title": s["title"], "trigger_hint": s["trigger_hint"],
                    "content": s["content"]} for s in db.list_sops(service=inc["service"])]
    return inc


@app.post("/api/incidents/{inc_id}/brief")
def incident_brief(inc_id: str):
    inc = _find_incident(inc_id)
    if not inc:
        return JSONResponse({"error": "not found"}, status_code=404)
    return ai_gateway.incident_brief(inc)


@app.post("/api/incidents/{inc_id}/rca")
def incident_rca(inc_id: str, user=Depends(current_user)):
    require(user, "ai_actions")
    inc = _find_incident(inc_id)
    if not inc:
        return JSONResponse({"error": "not found"}, status_code=404)
    result = ai_gateway.generate_rca(inc, REMEDIATIONS.get(inc["service"], []))
    tenant = SERVICE_META.get(inc["service"], {}).get("tenant")
    try:
        db.save_rca(inc_id, result["mode"], result["rca"])
        db.add_incident_event(inc_id, "rca_generated", f"RCA draft by {result['mode']}")
        if tenant:
            db.add_knowledge(tenant, f"RCA: {inc['title']}",
                             inc.get("signals", []), result["rca"], f"rca:{inc_id}")
    except Exception:
        pass
    return result


class CommentBody(BaseModel):
    comment: str


@app.get("/api/incidents/{inc_id}/comments")
def get_comments(inc_id: str):
    return {"comments": db.list_comments(inc_id)}


@app.post("/api/incidents/{inc_id}/comments")
def post_comment(inc_id: str, body: CommentBody, user=Depends(current_user)):
    db.add_comment(inc_id, user["email"], body.comment)
    return {"ok": True, "comments": db.list_comments(inc_id)}


# ---------------------------------------------------------------- runbooks
@app.get("/api/runbooks")
def runbooks():
    return {"runbooks": RUNBOOKS.catalog(), "audit": db.list_audit()}


class ExecuteBody(BaseModel):
    approved_by: str | None = None


@app.post("/api/runbooks/{rb_id}/execute")
def execute_runbook(rb_id: str, body: ExecuteBody, user=Depends(current_user)):
    require(user, "execute_runbooks")
    if body.approved_by:
        require(user, "approve_tier2")
        body.approved_by = f"{body.approved_by} ({user['email']})"
    result = RUNBOOKS.execute(rb_id, body.approved_by, triggered_by=user["email"])
    if result.get("ok"):
        rb = RUNBOOKS.get(rb_id)
        svc = rb.get("match", {}).get("service")
        REMEDIATIONS.setdefault(svc, []).append(result)
        db.log_audit(user["email"], "runbook_executed", rb_id,
                     {"tier": rb["tier"], "verification": result["verification"]["status"]})
        db.store_metric_samples(WORLD.metrics)
    return result


# ---------------------------------------------------------------- copilot
class CopilotBody(BaseModel):
    question: str


@app.post("/api/copilot")
def copilot(body: CopilotBody):
    incs = _incidents()
    context = {
        "incidents": [{k: i[k] for k in ("id", "service", "severity", "status", "title",
                                         "signals", "owner", "oncall")} for i in incs],
        "changes": WORLD.changes,
        "recommended_runbooks": [{"id": r["id"], "name": r["name"], "tier": r["tier"]}
                                 for i in incs for r in RUNBOOKS.recommend(i)],
        "sops": [{"application": s["application"], "title": s["title"],
                  "when_to_use": s["trigger_hint"], "steps": s["content"]}
                 for i in incs for s in db.list_sops(service=i["service"])],
        "service_owners": SERVICE_META,
    }
    result = ai_gateway.copilot_answer(body.question, context)
    db.add_chat(body.question, result["answer"], result["mode"])
    return result


@app.get("/api/copilot/history")
def copilot_history():
    return {"history": db.chat_history()}


# ================================================================ ADMINISTRATION
# ---- AI providers ----
class ProviderBody(BaseModel):
    provider: str
    api_key: str | None = None
    endpoint: str | None = None
    model: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None


@app.get("/api/admin/providers")
def providers():
    return {"providers": db.list_providers(), "status": HUB.status(),
            "default_models": DEFAULT_MODELS}


@app.post("/api/admin/providers")
def save_provider(body: ProviderBody, user=Depends(current_user)):
    require(user, "admin_config")
    if body.provider not in DEFAULT_MODELS:
        return JSONResponse({"error": "provider must be openai | anthropic | azure"}, status_code=400)
    key = body.api_key if (body.api_key and "…" not in body.api_key) else None
    db.upsert_provider(body.provider, api_key=key, endpoint=body.endpoint,
                       model=body.model, enabled=body.enabled, is_default=body.is_default)
    db.log_audit(user["email"], "provider_saved", body.provider,
                 {"model": body.model, "default": body.is_default, "key_changed": bool(key)})
    return {"ok": True, "providers": db.list_providers()}


@app.post("/api/admin/providers/{provider}/test")
def test_provider(provider: str):
    return HUB.test(provider)


# ---- log sources / ingestion ----
@app.get("/api/admin/sources")
def sources():
    return {"sources": db.list_sources(), "total_lines": db.logs_count()}


class IngestBody(BaseModel):
    name: str
    type: str           # paste | url
    text: str | None = None
    url: str | None = None
    service_hint: str | None = None


@app.post("/api/admin/ingest")
def ingest(body: IngestBody, user=Depends(current_user)):
    require(user, "ingest")
    db.log_audit(user["email"], "logs_ingested", body.name, {"type": body.type, "url": body.url})
    if body.type == "url":
        if not body.url:
            return JSONResponse({"error": "url required"}, status_code=400)
        try:
            req = urllib.request.Request(body.url, headers={"User-Agent": "NEXUS-OpsAI/2.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read(8_000_000).decode("utf-8", errors="replace")
        except Exception as e:
            return JSONResponse({"error": f"fetch failed: {e}"}, status_code=400)
    else:
        text = body.text or ""
    if not text.strip():
        return JSONResponse({"error": "no log content"}, status_code=400)

    entries = log_engine.parse_uploaded(text)
    if body.service_hint:
        for e in entries:
            if e["service"] == "uploaded":
                e["service"] = body.service_hint
    sid = db.create_source(body.name, body.type,
                           {"url": body.url} if body.url else {})
    db.insert_logs(entries, sid)
    clusters = log_engine.cluster_logs(entries, 1)
    return {"ok": True, "source_id": sid, "parsed": len(entries),
            "clusters": clusters[:15]}


@app.delete("/api/admin/sources/{source_id}")
def remove_source(source_id: int):
    db.delete_source(source_id)
    return {"ok": True}


# ---- database connections ----
class ConnectionBody(BaseModel):
    name: str
    engine: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    dbname: str = ""
    username: str = ""
    password: str = ""
    pool_min: int = 2
    pool_max: int = 10
    monitor_pool: bool = True


@app.get("/api/admin/connections")
def connections():
    return {"connections": db.list_connections()}


@app.post("/api/admin/connections")
def add_connection(body: ConnectionBody, user=Depends(current_user)):
    require(user, "admin_config")
    cid = db.create_connection(body.model_dump())
    db.log_audit(user["email"], "connection_added", body.name,
                 {"engine": body.engine, "host": body.host, "pool": [body.pool_min, body.pool_max]})
    return {"ok": True, "id": cid, "connections": db.list_connections()}


@app.post("/api/admin/connections/{conn_id}/test")
def test_connection(conn_id: int):
    c = db.get_connection(conn_id)
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    if c["engine"] != "postgresql":
        db.set_connection_status(conn_id, "unsupported-engine")
        return {"ok": False, "error": f"live test currently supports postgresql "
                                      f"(got {c['engine']}); connection saved for monitoring config"}
    try:
        import psycopg2
        conn = psycopg2.connect(host=c["host"], port=c["port"], dbname=c["dbname"],
                                user=c["username"], password=c["password"], connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT version(), (SELECT count(*) FROM pg_stat_activity)")
        version, active = cur.fetchone()
        conn.close()
        db.set_connection_status(conn_id, "connected")
        return {"ok": True, "version": version.split(",")[0], "active_connections": active,
                "pool": {"min": c["pool_min"], "max": c["pool_max"],
                         "utilization_pct": round(100 * active / max(c["pool_max"], 1), 1)}}
    except Exception as e:
        db.set_connection_status(conn_id, "failed")
        return {"ok": False, "error": str(e)[:250]}


@app.delete("/api/admin/connections/{conn_id}")
def remove_connection(conn_id: int):
    db.delete_connection(conn_id)
    return {"ok": True}


# ---- thresholds ----
class ThresholdUpdate(BaseModel):
    metric: str
    warn: float
    critical: float


@app.get("/api/config")
def get_config():
    return {"thresholds": _thresholds(), "prediction": _pred_cfg(),
            "ai": HUB.status(), "platform": FILE_CONFIG["platform"]}


@app.post("/api/config/threshold")
def set_threshold(body: ThresholdUpdate, user=Depends(current_user)):
    require(user, "admin_config")
    th = _thresholds()
    if body.metric not in th:
        return JSONResponse({"error": "unknown metric"}, status_code=400)
    th[body.metric] = {"warn": body.warn, "critical": body.critical}
    db.set_setting("thresholds", th)
    db.log_audit(user["email"], "threshold_changed", body.metric,
                 {"warn": body.warn, "critical": body.critical})
    return {"ok": True, "thresholds": th}


# ---- applications / knowledge / governance ----
class ApplicationBody(BaseModel):
    tenant: str
    name: str
    owner_team: str = ""
    oncall_email: str = ""
    criticality: str = "medium"
    description: str = ""
    services: list[str] = []


@app.get("/api/admin/applications")
def applications(tenant: str | None = None):
    return {"applications": db.list_applications(tenant)}


@app.post("/api/admin/applications")
def add_application(body: ApplicationBody, user=Depends(current_user)):
    require(user, "admin_config")
    app_id = db.upsert_application(body.tenant, body.name, body.owner_team, body.oncall_email,
                                   body.criticality, body.description, body.services)
    db.log_audit(user["email"], "application_registered", body.name,
                 {"tenant": body.tenant, "services": body.services})
    return {"ok": True, "id": app_id, "applications": db.list_applications()}


# ---- full application onboarding (collect everything, act on it) ----
class PatternIn(BaseModel):
    name: str
    pattern: str
    severity: str = "error"
    description: str = ""


class SopIn(BaseModel):
    title: str
    trigger_hint: str = ""
    content: str = ""


class DatabaseIn(BaseModel):
    name: str
    engine: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    dbname: str = ""
    username: str = ""
    password: str = ""
    pool_min: int = 2
    pool_max: int = 10


class OnboardBody(BaseModel):
    tenant: str
    name: str
    description: str = ""
    owner_team: str = ""
    oncall_email: str = ""
    criticality: str = "medium"
    business_impact: str = ""
    sla_target: str = ""
    environment: str = "production"
    services: list[str] = []
    dependencies_upstream: list[str] = []
    dependencies_downstream: list[str] = []
    log_locations: list[str] = []
    log_sample_text: str | None = None
    log_sample_url: str | None = None
    patterns: list[PatternIn] = []
    databases: list[DatabaseIn] = []
    sops: list[SopIn] = []


@app.post("/api/admin/applications/onboard")
def onboard_application(body: OnboardBody, user=Depends(current_user)):
    require(user, "admin_config")
    if not body.services:
        body.services = [body.name.lower().replace(" ", "-")]

    app_id = db.upsert_application(body.tenant, body.name, body.owner_team, body.oncall_email,
                                   body.criticality, body.description, body.services)
    db.set_application_profile(app_id, {
        "business_impact": body.business_impact, "sla_target": body.sla_target,
        "environment": body.environment, "log_locations": body.log_locations,
        "dependencies": {"upstream": body.dependencies_upstream,
                         "downstream": body.dependencies_downstream},
        "onboarded_by": user["email"],
    })
    for p in body.patterns:
        db.add_pattern(app_id, p.name, p.pattern, p.severity, p.description)
    for s in body.sops:
        db.add_sop(app_id, s.title, s.trigger_hint, s.content)
    conn_ids = []
    for d in body.databases:
        conn_ids.append(db.create_connection({**d.model_dump(), "monitor_pool": True}))

    ingested = 0
    if body.log_sample_url or (body.log_sample_text or "").strip():
        text = body.log_sample_text or ""
        if body.log_sample_url:
            try:
                req = urllib.request.Request(body.log_sample_url,
                                             headers={"User-Agent": "NEXUS-OpsAI/2.2"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    text = r.read(8_000_000).decode("utf-8", errors="replace")
            except Exception:
                text = body.log_sample_text or ""
        entries = log_engine.parse_uploaded(text)
        for e in entries:
            if e["service"] == "uploaded":
                e["service"] = body.services[0]
        if entries:
            sid = db.create_source(f"{body.name} onboarding logs", "onboarding",
                                   {"url": body.log_sample_url, "locations": body.log_locations})
            db.insert_logs(entries, sid)
            ingested = len(entries)

    db.log_audit(user["email"], "application_onboarded", body.name, {
        "tenant": body.tenant, "services": body.services,
        "patterns": len(body.patterns), "sops": len(body.sops),
        "databases": len(conn_ids), "log_lines": ingested,
    })
    db.add_notification(body.tenant, "info", f"Application onboarded: {body.name}",
                        f"{len(body.services)} service(s), {len(body.patterns)} watch pattern(s), "
                        f"{len(body.sops)} SOP(s), {len(conn_ids)} database(s), "
                        f"{ingested} log lines ingested.")
    return {"ok": True, "application_id": app_id,
            "summary": {"services": body.services, "patterns": len(body.patterns),
                        "sops": len(body.sops), "databases": len(conn_ids),
                        "log_lines_ingested": ingested}}


@app.get("/api/admin/applications/{app_id}/detail")
def application_detail(app_id: int):
    apps = [a for a in db.list_applications() if a["id"] == app_id]
    if not apps:
        return JSONResponse({"error": "not found"}, status_code=404)
    a = apps[0]
    a["patterns"] = db.list_patterns(app_id)
    a["sops"] = db.list_sops(app_id)
    return a


@app.get("/api/knowledge")
def knowledge(tenant: str | None = None):
    return {"articles": db.list_knowledge(tenant)}


@app.get("/api/notifications")
def notifications(tenant: str | None = None):
    return {"notifications": db.list_notifications(tenant)}


@app.get("/api/admin/ai-usage")
def ai_usage(user=Depends(current_user)):
    require(user, "admin_config")
    return {"usage": db.ai_usage_summary()}


@app.get("/api/admin/audit-log")
def audit_log(user=Depends(current_user)):
    require(user, "admin_config")
    return {"audit": db.list_audit_log()}


@app.get("/api/admin/db-stats")
def db_stats():
    return {"tables": db.table_stats()}


# ---------------------------------------------------------------- demo control
@app.post("/api/demo/reset")
def demo_reset():
    WORLD.reset()
    REMEDIATIONS.clear()
    RUNBOOKS.audit.clear()
    _NOTIFIED.clear()
    try:
        db.store_metric_samples(WORLD.metrics)
    except Exception:
        pass
    return {"ok": True, "reset_at": time.time()}


# ---------------------------------------------------------------- frontend (React build)
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}")
    def spa(path: str):
        target = DIST / path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")     # SPA fallback
else:
    @app.get("/")
    def index_fallback():
        return FileResponse(ROOT / "static" / "index.html")
