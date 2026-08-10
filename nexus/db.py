"""PostgreSQL persistence layer.

Everything a client configures or the platform learns lives here:
AI provider credentials, data sources, database connections, thresholds,
ingested logs, incident history, runbook audit trail, copilot transcript.
"""
from __future__ import annotations

import json
import os
import time

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nexusopsai")

_pool: ThreadedConnectionPool | None = None


def init_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
    return _pool


class Cur:
    """Context manager: pooled connection + dict cursor + commit."""
    def __enter__(self):
        self.conn = init_pool().getconn()
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return self.cur

    def __exit__(self, exc_type, *a):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.cur.close()
        _pool.putconn(self.conn)
        return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ai_providers (
  provider TEXT PRIMARY KEY,              -- openai | anthropic | azure
  api_key TEXT,
  endpoint TEXT,                          -- azure endpoint / custom base url
  model TEXT,
  enabled BOOLEAN DEFAULT true,
  is_default BOOLEAN DEFAULT false,
  last_test_status TEXT,
  last_test_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS log_sources (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,                     -- demo | paste | url | file
  config JSONB DEFAULT '{}'::jsonb,
  line_count INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS logs (
  id BIGSERIAL PRIMARY KEY,
  ts DOUBLE PRECISION NOT NULL,
  service TEXT NOT NULL,
  level TEXT NOT NULL,
  message TEXT NOT NULL,
  source_id INT REFERENCES log_sources(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_source ON logs(source_id);
CREATE TABLE IF NOT EXISTS db_connections (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  engine TEXT NOT NULL DEFAULT 'postgresql',
  host TEXT, port INT, dbname TEXT, username TEXT, password TEXT,
  pool_min INT DEFAULT 2, pool_max INT DEFAULT 10,
  monitor_pool BOOLEAN DEFAULT true,
  status TEXT DEFAULT 'unverified',
  last_checked TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS incidents (
  ext_id TEXT PRIMARY KEY,
  service TEXT, severity TEXT, status TEXT, title TEXT,
  signals JSONB, evidence JSONB, changes JSONB, blast JSONB,
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS runbook_audit (
  id SERIAL PRIMARY KEY,
  ts DOUBLE PRECISION,
  runbook TEXT, name TEXT, tier INT, outcome TEXT,
  approved_by TEXT, triggered_by TEXT,
  steps JSONB, verification JSONB
);
CREATE TABLE IF NOT EXISTS copilot_history (
  id SERIAL PRIMARY KEY,
  ts DOUBLE PRECISION,
  question TEXT, answer TEXT, provider TEXT
);

-- ============ multi-tenant / identity ============
CREATE TABLE IF NOT EXISTS tenants (
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  industry TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS roles (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  description TEXT,
  permissions JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  tenant_id INT REFERENCES tenants(id) ON DELETE CASCADE,
  email TEXT UNIQUE NOT NULL,
  display_name TEXT,
  role_id INT REFERENCES roles(id),
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ application catalog ============
CREATE TABLE IF NOT EXISTS applications (
  id SERIAL PRIMARY KEY,
  tenant_id INT REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  owner_team TEXT, oncall_email TEXT,
  criticality TEXT DEFAULT 'medium',
  tier TEXT DEFAULT 'standard',
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tenant_id, name)
);
CREATE TABLE IF NOT EXISTS application_services (
  id SERIAL PRIMARY KEY,
  application_id INT REFERENCES applications(id) ON DELETE CASCADE,
  service_name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS maintenance_windows (
  id SERIAL PRIMARY KEY,
  application_id INT REFERENCES applications(id) ON DELETE CASCADE,
  starts_at TIMESTAMPTZ, ends_at TIMESTAMPTZ, reason TEXT
);

-- ============ telemetry ============
CREATE TABLE IF NOT EXISTS metrics_catalog (
  id SERIAL PRIMARY KEY,
  metric TEXT UNIQUE NOT NULL,
  display_name TEXT, unit TEXT,
  direction TEXT DEFAULT 'higher_is_worse'
);
CREATE TABLE IF NOT EXISTS metric_samples (
  id BIGSERIAL PRIMARY KEY,
  service TEXT NOT NULL, metric TEXT NOT NULL,
  ts DOUBLE PRECISION NOT NULL, value DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples ON metric_samples(service, metric, ts DESC);
CREATE TABLE IF NOT EXISTS alerts (
  id BIGSERIAL PRIMARY KEY,
  ts DOUBLE PRECISION NOT NULL,
  service TEXT, metric TEXT, level TEXT, kind TEXT,   -- breach | prediction
  value DOUBLE PRECISION, threshold DOUBLE PRECISION,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS predictions_history (
  id BIGSERIAL PRIMARY KEY,
  ts DOUBLE PRECISION NOT NULL,
  service TEXT, metric TEXT,
  eta_minutes INT, confidence DOUBLE PRECISION, threshold DOUBLE PRECISION
);

-- ============ incident collaboration ============
CREATE TABLE IF NOT EXISTS incident_events (
  id BIGSERIAL PRIMARY KEY,
  incident_ext_id TEXT, ts DOUBLE PRECISION,
  kind TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS incident_comments (
  id SERIAL PRIMARY KEY,
  incident_ext_id TEXT, user_email TEXT,
  ts DOUBLE PRECISION, comment TEXT
);

-- ============ knowledge & automation ============
CREATE TABLE IF NOT EXISTS runbooks_catalog (
  id SERIAL PRIMARY KEY,
  runbook_id TEXT UNIQUE NOT NULL,
  name TEXT, tier INT, service TEXT,
  signals JSONB, steps JSONB, verify JSONB,
  enabled BOOLEAN DEFAULT true,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS rca_reports (
  id SERIAL PRIMARY KEY,
  incident_ext_id TEXT, ts DOUBLE PRECISION,
  provider TEXT, content TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_articles (
  id SERIAL PRIMARY KEY,
  tenant_id INT REFERENCES tenants(id) ON DELETE SET NULL,
  title TEXT NOT NULL, tags JSONB DEFAULT '[]'::jsonb,
  content TEXT, source TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ platform governance ============
CREATE TABLE IF NOT EXISTS ai_usage (
  id BIGSERIAL PRIMARY KEY,
  ts DOUBLE PRECISION NOT NULL,
  provider TEXT, model TEXT, feature TEXT,
  prompt_chars INT, completion_chars INT,
  latency_ms INT, status TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
  id BIGSERIAL PRIMARY KEY,
  ts DOUBLE PRECISION NOT NULL,
  user_email TEXT, action TEXT, entity TEXT,
  detail JSONB DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS notifications (
  id SERIAL PRIMARY KEY,
  ts DOUBLE PRECISION NOT NULL,
  tenant_id INT REFERENCES tenants(id) ON DELETE CASCADE,
  severity TEXT, title TEXT, body TEXT,
  read BOOLEAN DEFAULT false
);
"""


def init_schema():
    with Cur() as c:
        c.execute(SCHEMA)


# ---------------------------------------------------------------- settings
def get_setting(key: str, default=None):
    with Cur() as c:
        c.execute("SELECT value FROM settings WHERE key=%s", (key,))
        row = c.fetchone()
        return row["value"] if row else default


def set_setting(key: str, value):
    with Cur() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(%s,%s) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()",
            (key, json.dumps(value)))


# ---------------------------------------------------------------- providers
def list_providers(mask=True):
    with Cur() as c:
        c.execute("SELECT * FROM ai_providers ORDER BY provider")
        rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["configured"] = bool(r["api_key"])
        if mask and r["api_key"]:
            r["api_key"] = r["api_key"][:8] + "…" + r["api_key"][-4:]
        for k in ("last_test_at", "updated_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return rows


def get_provider(provider: str):
    with Cur() as c:
        c.execute("SELECT * FROM ai_providers WHERE provider=%s", (provider,))
        r = c.fetchone()
        return dict(r) if r else None


def upsert_provider(provider, api_key=None, endpoint=None, model=None,
                    enabled=None, is_default=None):
    existing = get_provider(provider) or {}
    api_key = api_key if api_key else existing.get("api_key")
    endpoint = endpoint if endpoint is not None else existing.get("endpoint")
    model = model if model is not None else existing.get("model")
    enabled = enabled if enabled is not None else existing.get("enabled", True)
    is_default = is_default if is_default is not None else existing.get("is_default", False)
    with Cur() as c:
        if is_default:
            c.execute("UPDATE ai_providers SET is_default=false")
        c.execute(
            "INSERT INTO ai_providers(provider,api_key,endpoint,model,enabled,is_default) "
            "VALUES(%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (provider) DO UPDATE SET api_key=EXCLUDED.api_key, "
            "endpoint=EXCLUDED.endpoint, model=EXCLUDED.model, enabled=EXCLUDED.enabled, "
            "is_default=EXCLUDED.is_default, updated_at=now()",
            (provider, api_key, endpoint, model, enabled, is_default))


def record_provider_test(provider, status):
    with Cur() as c:
        c.execute("UPDATE ai_providers SET last_test_status=%s, last_test_at=now() "
                  "WHERE provider=%s", (status, provider))


def default_provider():
    with Cur() as c:
        c.execute("SELECT * FROM ai_providers WHERE enabled AND api_key IS NOT NULL "
                  "ORDER BY is_default DESC, provider LIMIT 1")
        r = c.fetchone()
        return dict(r) if r else None


# ---------------------------------------------------------------- logs & sources
def create_source(name, type_, config=None):
    with Cur() as c:
        c.execute("INSERT INTO log_sources(name,type,config) VALUES(%s,%s,%s) RETURNING id",
                  (name, type_, json.dumps(config or {})))
        return c.fetchone()["id"]


def list_sources():
    with Cur() as c:
        c.execute("SELECT id,name,type,config,line_count,created_at FROM log_sources ORDER BY id")
        rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
    return rows


def delete_source(source_id):
    with Cur() as c:
        c.execute("DELETE FROM log_sources WHERE id=%s", (source_id,))


def insert_logs(entries: list[dict], source_id: int):
    with Cur() as c:
        psycopg2.extras.execute_values(
            c, "INSERT INTO logs(ts,service,level,message,source_id) VALUES %s",
            [(e["ts"], e["service"], e["level"], e["message"], source_id) for e in entries])
        c.execute("UPDATE log_sources SET line_count=line_count+%s WHERE id=%s",
                  (len(entries), source_id))


def fetch_logs(limit=25000, source_id=None):
    with Cur() as c:
        if source_id:
            c.execute("SELECT ts,service,level,message FROM logs WHERE source_id=%s "
                      "ORDER BY ts DESC LIMIT %s", (source_id, limit))
        else:
            c.execute("SELECT ts,service,level,message FROM logs ORDER BY ts DESC LIMIT %s",
                      (limit,))
        return [dict(r) for r in c.fetchall()]


def logs_count():
    with Cur() as c:
        c.execute("SELECT count(*) AS n FROM logs")
        return c.fetchone()["n"]


# ---------------------------------------------------------------- db connections
def create_connection(d: dict):
    with Cur() as c:
        c.execute(
            "INSERT INTO db_connections(name,engine,host,port,dbname,username,password,"
            "pool_min,pool_max,monitor_pool) VALUES(%(name)s,%(engine)s,%(host)s,%(port)s,"
            "%(dbname)s,%(username)s,%(password)s,%(pool_min)s,%(pool_max)s,%(monitor_pool)s) "
            "RETURNING id", d)
        return c.fetchone()["id"]


def list_connections():
    with Cur() as c:
        c.execute("SELECT id,name,engine,host,port,dbname,username,pool_min,pool_max,"
                  "monitor_pool,status,last_checked FROM db_connections ORDER BY id")
        rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        if r.get("last_checked"):
            r["last_checked"] = r["last_checked"].isoformat()
    return rows


def get_connection(conn_id):
    with Cur() as c:
        c.execute("SELECT * FROM db_connections WHERE id=%s", (conn_id,))
        r = c.fetchone()
        return dict(r) if r else None


def set_connection_status(conn_id, status):
    with Cur() as c:
        c.execute("UPDATE db_connections SET status=%s, last_checked=now() WHERE id=%s",
                  (status, conn_id))


def delete_connection(conn_id):
    with Cur() as c:
        c.execute("DELETE FROM db_connections WHERE id=%s", (conn_id,))


# ---------------------------------------------------------------- incidents / audit / chat
def upsert_incidents(incidents: list[dict]):
    with Cur() as c:
        for i in incidents:
            c.execute(
                "INSERT INTO incidents(ext_id,service,severity,status,title,signals,evidence,"
                "changes,blast) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (ext_id) DO UPDATE SET severity=EXCLUDED.severity, "
                "status=EXCLUDED.status, title=EXCLUDED.title, signals=EXCLUDED.signals, "
                "evidence=EXCLUDED.evidence, last_seen=now()",
                (i["id"], i["service"], i["severity"], i["status"], i["title"],
                 json.dumps(i["signals"]), json.dumps(i["evidence"]),
                 json.dumps(i.get("changes", [])), json.dumps(i.get("blast_radius", {}))))


def add_audit(entry: dict):
    with Cur() as c:
        c.execute(
            "INSERT INTO runbook_audit(ts,runbook,name,tier,outcome,approved_by,triggered_by,"
            "steps,verification) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (entry["ts"], entry["runbook"], entry["name"], entry["tier"], entry["outcome"],
             entry.get("approved_by"), entry.get("triggered_by"),
             json.dumps(entry.get("steps", [])), json.dumps(entry.get("verification"))))


def list_audit(limit=50):
    with Cur() as c:
        c.execute("SELECT * FROM runbook_audit ORDER BY id DESC LIMIT %s", (limit,))
        return [dict(r) for r in c.fetchall()]


def audit_count():
    with Cur() as c:
        c.execute("SELECT count(*) AS n FROM runbook_audit")
        return c.fetchone()["n"]


# ---------------------------------------------------------------- tenants / users / rbac
def list_tenants():
    with Cur() as c:
        c.execute("SELECT id,slug,name,industry FROM tenants ORDER BY id")
        return [dict(r) for r in c.fetchall()]


def upsert_tenant(slug, name, industry=None):
    with Cur() as c:
        c.execute("INSERT INTO tenants(slug,name,industry) VALUES(%s,%s,%s) "
                  "ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id",
                  (slug, name, industry))
        return c.fetchone()["id"]


def upsert_role(name, description, permissions):
    with Cur() as c:
        c.execute("INSERT INTO roles(name,description,permissions) VALUES(%s,%s,%s) "
                  "ON CONFLICT (name) DO UPDATE SET permissions=EXCLUDED.permissions RETURNING id",
                  (name, description, json.dumps(permissions)))
        return c.fetchone()["id"]


def upsert_user(email, display_name, tenant_slug, role_name):
    with Cur() as c:
        c.execute(
            "INSERT INTO users(email,display_name,tenant_id,role_id) "
            "SELECT %s,%s,t.id,r.id FROM tenants t, roles r WHERE t.slug=%s AND r.name=%s "
            "ON CONFLICT (email) DO UPDATE SET display_name=EXCLUDED.display_name, "
            "tenant_id=EXCLUDED.tenant_id, role_id=EXCLUDED.role_id",
            (email, display_name, tenant_slug, role_name))


def list_users():
    with Cur() as c:
        c.execute(
            "SELECT u.id,u.email,u.display_name,u.active,t.slug AS tenant,t.name AS tenant_name,"
            "r.name AS role,r.permissions FROM users u "
            "JOIN tenants t ON t.id=u.tenant_id JOIN roles r ON r.id=u.role_id ORDER BY t.slug,u.email")
        return [dict(r) for r in c.fetchall()]


def get_user(email):
    with Cur() as c:
        c.execute(
            "SELECT u.email,u.display_name,t.slug AS tenant,t.name AS tenant_name,"
            "r.name AS role,r.permissions FROM users u "
            "JOIN tenants t ON t.id=u.tenant_id JOIN roles r ON r.id=u.role_id "
            "WHERE u.email=%s AND u.active", (email,))
        r = c.fetchone()
        return dict(r) if r else None


# ---------------------------------------------------------------- applications
def upsert_application(tenant_slug, name, owner_team, oncall_email, criticality,
                       description, services):
    with Cur() as c:
        c.execute(
            "INSERT INTO applications(tenant_id,name,owner_team,oncall_email,criticality,description) "
            "SELECT t.id,%s,%s,%s,%s,%s FROM tenants t WHERE t.slug=%s "
            "ON CONFLICT (tenant_id,name) DO UPDATE SET owner_team=EXCLUDED.owner_team, "
            "oncall_email=EXCLUDED.oncall_email, criticality=EXCLUDED.criticality RETURNING id",
            (name, owner_team, oncall_email, criticality, description, tenant_slug))
        app_id = c.fetchone()["id"]
        for svc in services:
            c.execute("INSERT INTO application_services(application_id,service_name) VALUES(%s,%s) "
                      "ON CONFLICT (service_name) DO UPDATE SET application_id=EXCLUDED.application_id",
                      (app_id, svc))
        return app_id


def list_applications(tenant_slug=None):
    with Cur() as c:
        q = ("SELECT a.id,a.name,a.owner_team,a.oncall_email,a.criticality,a.tier,a.description,"
             "t.slug AS tenant,t.name AS tenant_name,"
             "COALESCE(json_agg(s.service_name) FILTER (WHERE s.service_name IS NOT NULL),'[]') AS services "
             "FROM applications a JOIN tenants t ON t.id=a.tenant_id "
             "LEFT JOIN application_services s ON s.application_id=a.id ")
        if tenant_slug:
            c.execute(q + "WHERE t.slug=%s GROUP BY a.id,t.slug,t.name ORDER BY a.name", (tenant_slug,))
        else:
            c.execute(q + "GROUP BY a.id,t.slug,t.name ORDER BY t.slug,a.name")
        return [dict(r) for r in c.fetchall()]


def services_for_tenant(tenant_slug):
    with Cur() as c:
        c.execute("SELECT s.service_name FROM application_services s "
                  "JOIN applications a ON a.id=s.application_id "
                  "JOIN tenants t ON t.id=a.tenant_id WHERE t.slug=%s", (tenant_slug,))
        return [r["service_name"] for r in c.fetchall()]


# ---------------------------------------------------------------- telemetry persistence
def upsert_metrics_catalog(entries):
    with Cur() as c:
        for m, (name, unit) in entries.items():
            c.execute("INSERT INTO metrics_catalog(metric,display_name,unit) VALUES(%s,%s,%s) "
                      "ON CONFLICT (metric) DO NOTHING", (m, name, unit))


def store_metric_samples(metrics: dict):
    """Persist the latest snapshot of every series (replace-all, demo scale)."""
    with Cur() as c:
        c.execute("TRUNCATE metric_samples")
        rows = [(svc, m, ts, v)
                for svc, mm in metrics.items()
                for m, series in mm.items()
                for ts, v in series]
        psycopg2.extras.execute_values(
            c, "INSERT INTO metric_samples(service,metric,ts,value) VALUES %s", rows,
            page_size=2000)


def record_alerts(breaches, preds):
    now = time.time()
    with Cur() as c:
        for b in breaches:
            c.execute("INSERT INTO alerts(ts,service,metric,level,kind,value,threshold,detail) "
                      "VALUES(%s,%s,%s,%s,'breach',%s,%s,%s)",
                      (now, b["service"], b["metric"], b["level"], b["value"], b["threshold"], b["title"]))
        for p in preds:
            c.execute("INSERT INTO predictions_history(ts,service,metric,eta_minutes,confidence,threshold) "
                      "VALUES(%s,%s,%s,%s,%s,%s)",
                      (now, p["service"], p["metric"], p["eta_minutes"], p["confidence"], p["threshold"]))


def add_incident_event(ext_id, kind, detail):
    with Cur() as c:
        c.execute("INSERT INTO incident_events(incident_ext_id,ts,kind,detail) VALUES(%s,%s,%s,%s)",
                  (ext_id, time.time(), kind, detail))


def add_comment(ext_id, user_email, comment):
    with Cur() as c:
        c.execute("INSERT INTO incident_comments(incident_ext_id,user_email,ts,comment) "
                  "VALUES(%s,%s,%s,%s)", (ext_id, user_email, time.time(), comment))


def list_comments(ext_id):
    with Cur() as c:
        c.execute("SELECT user_email,ts,comment FROM incident_comments "
                  "WHERE incident_ext_id=%s ORDER BY id", (ext_id,))
        return [dict(r) for r in c.fetchall()]


# ---------------------------------------------------------------- knowledge / runbooks / rca
def sync_runbooks_catalog(runbooks):
    with Cur() as c:
        for r in runbooks:
            c.execute(
                "INSERT INTO runbooks_catalog(runbook_id,name,tier,service,signals,steps,verify) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (runbook_id) DO UPDATE SET "
                "name=EXCLUDED.name, tier=EXCLUDED.tier, steps=EXCLUDED.steps, "
                "verify=EXCLUDED.verify, updated_at=now()",
                (r["id"], r["name"], r["tier"], r.get("match", {}).get("service"),
                 json.dumps(r.get("match", {}).get("signals", [])),
                 json.dumps(r.get("steps", [])), json.dumps(r.get("verify", {}))))


def save_rca(ext_id, provider, content):
    with Cur() as c:
        c.execute("INSERT INTO rca_reports(incident_ext_id,ts,provider,content) VALUES(%s,%s,%s,%s)",
                  (ext_id, time.time(), provider, content))


def add_knowledge(tenant_slug, title, tags, content, source):
    with Cur() as c:
        c.execute("INSERT INTO knowledge_articles(tenant_id,title,tags,content,source) "
                  "SELECT t.id,%s,%s,%s,%s FROM tenants t WHERE t.slug=%s",
                  (title, json.dumps(tags), content, source, tenant_slug))


def list_knowledge(tenant_slug=None):
    with Cur() as c:
        if tenant_slug:
            c.execute("SELECT k.id,k.title,k.tags,k.source,k.created_at,t.slug AS tenant "
                      "FROM knowledge_articles k LEFT JOIN tenants t ON t.id=k.tenant_id "
                      "WHERE t.slug=%s ORDER BY k.id DESC", (tenant_slug,))
        else:
            c.execute("SELECT k.id,k.title,k.tags,k.source,k.created_at,t.slug AS tenant "
                      "FROM knowledge_articles k LEFT JOIN tenants t ON t.id=k.tenant_id "
                      "ORDER BY k.id DESC")
        rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
    return rows


# ---------------------------------------------------------------- governance
def log_ai_usage(provider, model, feature, prompt_chars, completion_chars, latency_ms, status):
    with Cur() as c:
        c.execute("INSERT INTO ai_usage(ts,provider,model,feature,prompt_chars,completion_chars,"
                  "latency_ms,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                  (time.time(), provider, model, feature, prompt_chars, completion_chars,
                   latency_ms, status))


def ai_usage_summary():
    with Cur() as c:
        c.execute("SELECT provider, count(*) AS calls, "
                  "COALESCE(avg(latency_ms),0)::int AS avg_latency_ms, "
                  "COALESCE(sum(prompt_chars),0) AS prompt_chars, "
                  "COALESCE(sum(completion_chars),0) AS completion_chars "
                  "FROM ai_usage GROUP BY provider ORDER BY calls DESC")
        return [dict(r) for r in c.fetchall()]


def log_audit(user_email, action, entity, detail=None):
    with Cur() as c:
        c.execute("INSERT INTO audit_log(ts,user_email,action,entity,detail) VALUES(%s,%s,%s,%s,%s)",
                  (time.time(), user_email, action, entity, json.dumps(detail or {})))


def list_audit_log(limit=50):
    with Cur() as c:
        c.execute("SELECT ts,user_email,action,entity,detail FROM audit_log ORDER BY id DESC LIMIT %s",
                  (limit,))
        return [dict(r) for r in c.fetchall()]


def add_notification(tenant_slug, severity, title, body):
    with Cur() as c:
        c.execute("INSERT INTO notifications(ts,tenant_id,severity,title,body) "
                  "SELECT %s,t.id,%s,%s,%s FROM tenants t WHERE t.slug=%s",
                  (time.time(), severity, title, body, tenant_slug))


def list_notifications(tenant_slug=None, limit=30):
    with Cur() as c:
        if tenant_slug:
            c.execute("SELECT n.id,n.ts,n.severity,n.title,n.body,n.read,t.slug AS tenant "
                      "FROM notifications n JOIN tenants t ON t.id=n.tenant_id "
                      "WHERE t.slug=%s ORDER BY n.id DESC LIMIT %s", (tenant_slug, limit))
        else:
            c.execute("SELECT n.id,n.ts,n.severity,n.title,n.body,n.read,t.slug AS tenant "
                      "FROM notifications n JOIN tenants t ON t.id=n.tenant_id "
                      "ORDER BY n.id DESC LIMIT %s", (limit,))
        return [dict(r) for r in c.fetchall()]


def table_stats():
    with Cur() as c:
        c.execute("SELECT relname FROM pg_stat_user_tables ORDER BY relname")
        names = [r["relname"] for r in c.fetchall()]
        out = []
        for n in names:
            c.execute(f'SELECT count(*) AS n FROM "{n}"')   # table names come from pg catalog, not user input
            out.append({"table": n, "rows": c.fetchone()["n"]})
        return out


def add_chat(question, answer, provider):
    with Cur() as c:
        c.execute("INSERT INTO copilot_history(ts,question,answer,provider) VALUES(%s,%s,%s,%s)",
                  (time.time(), question, answer, provider))


def chat_history(limit=40):
    with Cur() as c:
        c.execute("SELECT ts,question,answer,provider FROM copilot_history ORDER BY id DESC LIMIT %s",
                  (limit,))
        return list(reversed([dict(r) for r in c.fetchall()]))
