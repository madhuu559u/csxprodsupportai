import { useEffect, useState } from 'react'
import { api, post, del, PROVIDER_LABEL, fmtAgo } from '../api'
import { PageHead } from '../bits'

export default function Admin() {
  const [tab, setTab] = useState('providers')
  return (
    <div className="page">
      <PageHead icon="⚙" tint="linear-gradient(135deg,#706e6b,#444)" crumb="Setup"
        title="Administration"
        desc="Client-configurable: AI provider keys, log sources, database connections with pool monitoring, and alert thresholds. Everything persists in PostgreSQL." />
      <div className="appnav" style={{ position: 'static', borderRadius: '.5rem', border: '1px solid var(--border)', marginBottom: '1rem' }}>
        {[['providers', 'AI Providers'], ['apps', 'Applications'], ['sources', 'Data Sources'],
          ['connections', 'Database Connections'], ['thresholds', 'Alert Thresholds'], ['gov', 'Users & Governance']]
          .map(([k, label]) => (
            <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{label}</button>
          ))}
      </div>
      {tab === 'providers' && <Providers />}
      {tab === 'apps' && <Applications />}
      {tab === 'sources' && <Sources />}
      {tab === 'connections' && <Connections />}
      {tab === 'thresholds' && <Thresholds />}
      {tab === 'gov' && <Governance />}
    </div>
  )
}

/* ---------------- AI Providers ---------------- */
function Providers() {
  const [data, setData] = useState(null)
  const [form, setForm] = useState({ provider: 'openai', api_key: '', endpoint: '', model: '', is_default: false })
  const [testResult, setTestResult] = useState({})
  const [msg, setMsg] = useState('')

  const load = async () => setData(await api('/api/admin/providers'))
  useEffect(() => { load() }, [])

  const save = async () => {
    const body = { ...form, model: form.model || null, endpoint: form.endpoint || null, enabled: true }
    if (!body.api_key) delete body.api_key
    const r = await post('/api/admin/providers', body)
    setMsg(r.ok ? 'Saved.' : r.error || 'Failed')
    setForm((f) => ({ ...f, api_key: '' }))
    load()
  }
  const test = async (p) => {
    setTestResult((t) => ({ ...t, [p]: { busy: true } }))
    const r = await post(`/api/admin/providers/${p}/test`)
    setTestResult((t) => ({ ...t, [p]: r }))
    load()
  }

  if (!data) return <div className="card spin">Loading…</div>
  return (
    <>
      <div className="card">
        <h2>Configured providers</h2>
        <div className="cardsub">The default provider serves all AI features; on failure the platform falls through to the next enabled provider, then to the built-in offline engine.</div>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>Provider</th><th>API key</th><th>Model / deployment</th><th>Default</th><th>Last test</th><th></th></tr></thead>
          <tbody>
            {data.providers.length === 0 && <tr><td colSpan="6" style={{ color: 'var(--muted)' }}>None yet — add one below.</td></tr>}
            {data.providers.map((p) => (
              <tr key={p.provider}>
                <td><b>{PROVIDER_LABEL[p.provider]}</b></td>
                <td className="mono">{p.configured ? p.api_key : '—'}</td>
                <td className="mono">{p.model || data.default_models[p.provider]}</td>
                <td>{p.is_default ? <span className="badge brand">default</span> : ''}</td>
                <td>{p.last_test_status
                  ? <span className={`badge ${p.last_test_status === 'passed' ? 'good' : 'sev1'}`}>{p.last_test_status}</span>
                  : <span className="badge neutral">never</span>}</td>
                <td>
                  <button className="btn sm" onClick={() => test(p.provider)}>Test</button>{' '}
                  {!p.is_default && <button className="btn sm" onClick={async () => { await post('/api/admin/providers', { provider: p.provider, is_default: true }); load() }}>Make default</button>}
                  {testResult[p.provider] && !testResult[p.provider].busy && (
                    <div style={{ fontSize: '.7rem', marginTop: 4, color: testResult[p.provider].ok ? 'var(--good)' : 'var(--serious)' }}>
                      {testResult[p.provider].ok ? `✓ live response: "${testResult[p.provider].response}"` : `✗ ${testResult[p.provider].error}`}
                    </div>
                  )}
                  {testResult[p.provider]?.busy && <span className="spin"> testing…</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      <div className="card">
        <h2>Add / update a provider</h2>
        <div className="formrow">
          <div className="field">
            <label>Provider</label>
            <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic Claude</option>
              <option value="azure">Azure OpenAI</option>
            </select>
          </div>
          <div className="field" style={{ gridColumn: 'span 2' }}>
            <label>API key {form.provider === 'azure' && '(Azure key)'}</label>
            <input type="password" value={form.api_key} placeholder="paste key — stored in PostgreSQL, masked in UI"
              onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
          </div>
          <div className="field">
            <label>Model {form.provider === 'azure' && '/ deployment name'}</label>
            <input value={form.model} placeholder={{ openai: 'gpt-4o-mini', anthropic: 'claude-opus-5', azure: 'my-gpt4o-deployment' }[form.provider]}
              onChange={(e) => setForm({ ...form, model: e.target.value })} />
          </div>
          {form.provider === 'azure' && (
            <div className="field" style={{ gridColumn: 'span 2' }}>
              <label>Azure endpoint</label>
              <input value={form.endpoint} placeholder="https://myresource.openai.azure.com"
                onChange={(e) => setForm({ ...form, endpoint: e.target.value })} />
            </div>
          )}
        </div>
        <label style={{ fontSize: '.78rem' }}>
          <input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} /> make this the default provider
        </label>
        <div style={{ marginTop: '.7rem' }}>
          <button className="btn brand" onClick={save}>Save provider</button>
          <span style={{ marginLeft: '.6rem', color: 'var(--good)', fontSize: '.76rem' }}>{msg}</span>
        </div>
      </div>
    </>
  )
}

/* ---------------- Data Sources (log ingestion) ---------------- */
function Sources() {
  const [data, setData] = useState(null)
  const [form, setForm] = useState({ name: '', type: 'paste', text: '', url: '', service_hint: '' })
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = async () => setData(await api('/api/admin/sources'))
  useEffect(() => { load() }, [])

  const ingest = async () => {
    setBusy(true); setResult(null)
    const r = await post('/api/admin/ingest', form)
    setResult(r); setBusy(false); load()
  }

  if (!data) return <div className="card spin">Loading…</div>
  return (
    <>
      <div className="card">
        <h2>Log sources ({data.total_lines.toLocaleString()} lines in PostgreSQL)</h2>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>ID</th><th>Name</th><th>Type</th><th>Lines</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {data.sources.map((s) => (
              <tr key={s.id}>
                <td>{s.id}</td><td><b>{s.name}</b></td><td><span className="badge neutral">{s.type}</span></td>
                <td>{s.line_count.toLocaleString()}</td>
                <td className="mono">{s.created_at.slice(0, 16).replace('T', ' ')}</td>
                <td>{s.type !== 'demo' && <button className="btn sm danger" onClick={async () => { await del(`/api/admin/sources/${s.id}`); load() }}>Delete</button>}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      <div className="card">
        <h2>Ingest logs</h2>
        <div className="cardsub">Paste raw logs from any system (Splunk / ELK export, kubectl, files) or fetch a log file directly from a URL. The engine parses, templates and clusters them so your company's patterns are mined automatically.</div>
        <div className="formrow">
          <div className="field"><label>Source name</label>
            <input value={form.name} placeholder="e.g. billing-svc prod logs" onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="field"><label>Type</label>
            <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              <option value="paste">Paste text</option><option value="url">Fetch from URL</option>
            </select></div>
          <div className="field"><label>Service name override (optional)</label>
            <input value={form.service_hint} placeholder="e.g. billing-svc" onChange={(e) => setForm({ ...form, service_hint: e.target.value })} /></div>
        </div>
        {form.type === 'paste' ? (
          <div className="field"><label>Raw log lines</label>
            <textarea value={form.text} placeholder="2026-08-09 14:21:08 ERROR [order-svc] SQLException ..." onChange={(e) => setForm({ ...form, text: e.target.value })} /></div>
        ) : (
          <div className="field"><label>URL</label>
            <input value={form.url} placeholder="https://raw.githubusercontent.com/.../app.log" onChange={(e) => setForm({ ...form, url: e.target.value })} /></div>
        )}
        <button className="btn brand" onClick={ingest} disabled={busy || !form.name}>{busy ? 'Ingesting…' : 'Parse & ingest'}</button>
        {result && (result.ok
          ? <div className="evd good" style={{ marginTop: '.6rem' }}>
              ✅ Parsed <b>{result.parsed.toLocaleString()}</b> lines into <b>{result.clusters.length}</b>+ patterns. Top:{' '}
              <span className="mono">{result.clusters[0]?.template.slice(0, 90)}</span> ({result.clusters[0]?.count}x)
            </div>
          : <div className="evd metric" style={{ marginTop: '.6rem' }}>⛔ {result.error}</div>)}
      </div>
    </>
  )
}

/* ---------------- Database Connections ---------------- */
function Connections() {
  const [data, setData] = useState(null)
  const [form, setForm] = useState({ name: '', engine: 'postgresql', host: 'localhost', port: 5432, dbname: '', username: '', password: '', pool_min: 2, pool_max: 10, monitor_pool: true })
  const [testRes, setTestRes] = useState({})

  const load = async () => setData(await api('/api/admin/connections'))
  useEffect(() => { load() }, [])

  const save = async () => { await post('/api/admin/connections', { ...form, port: +form.port, pool_min: +form.pool_min, pool_max: +form.pool_max }); load() }
  const test = async (id) => {
    setTestRes((t) => ({ ...t, [id]: { busy: true } }))
    const r = await post(`/api/admin/connections/${id}/test`)
    setTestRes((t) => ({ ...t, [id]: r })); load()
  }

  if (!data) return <div className="card spin">Loading…</div>
  return (
    <>
      <div className="card">
        <h2>Monitored database connections</h2>
        <div className="cardsub">Register the databases behind your applications. The platform verifies connectivity, tracks connection-pool sizing, and (with pool monitoring on) feeds utilization into predictive alerts — pool exhaustion is the #1 low-hanging fruit.</div>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>Name</th><th>Engine</th><th>Host</th><th>Database</th><th>Pool (min–max)</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {data.connections.length === 0 && <tr><td colSpan="7" style={{ color: 'var(--muted)' }}>None registered yet.</td></tr>}
            {data.connections.map((c) => (
              <tr key={c.id}>
                <td><b>{c.name}</b></td><td>{c.engine}</td>
                <td className="mono">{c.host}:{c.port}</td><td className="mono">{c.dbname}</td>
                <td>{c.pool_min}–{c.pool_max} {c.monitor_pool && <span className="badge brand">monitored</span>}</td>
                <td><span className={`badge ${c.status === 'connected' ? 'good' : c.status === 'failed' ? 'sev1' : 'neutral'}`}>{c.status}</span></td>
                <td>
                  <button className="btn sm" onClick={() => test(c.id)}>Test</button>{' '}
                  <button className="btn sm danger" onClick={async () => { await del(`/api/admin/connections/${c.id}`); load() }}>Delete</button>
                  {testRes[c.id] && !testRes[c.id].busy && (
                    <div style={{ fontSize: '.7rem', marginTop: 4, color: testRes[c.id].ok ? 'var(--good)' : 'var(--serious)' }}>
                      {testRes[c.id].ok
                        ? `✓ ${testRes[c.id].version} · ${testRes[c.id].active_connections} active conns · pool util ${testRes[c.id].pool.utilization_pct}%`
                        : `✗ ${testRes[c.id].error}`}
                    </div>
                  )}
                  {testRes[c.id]?.busy && <span className="spin"> testing…</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      <div className="card">
        <h2>Register a database</h2>
        <div className="formrow">
          {[['name', 'Connection name'], ['host', 'Host'], ['port', 'Port'], ['dbname', 'Database'], ['username', 'Username']].map(([k, label]) => (
            <div className="field" key={k}><label>{label}</label>
              <input value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></div>
          ))}
          <div className="field"><label>Password</label>
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
          <div className="field"><label>Engine</label>
            <select value={form.engine} onChange={(e) => setForm({ ...form, engine: e.target.value })}>
              <option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option>
              <option value="oracle">Oracle</option><option value="sqlserver">SQL Server</option>
            </select></div>
          <div className="field"><label>Pool min</label>
            <input type="number" value={form.pool_min} onChange={(e) => setForm({ ...form, pool_min: e.target.value })} /></div>
          <div className="field"><label>Pool max</label>
            <input type="number" value={form.pool_max} onChange={(e) => setForm({ ...form, pool_max: e.target.value })} /></div>
        </div>
        <label style={{ fontSize: '.78rem' }}>
          <input type="checkbox" checked={form.monitor_pool} onChange={(e) => setForm({ ...form, monitor_pool: e.target.checked })} /> monitor connection pool utilization
        </label>
        <div style={{ marginTop: '.7rem' }}>
          <button className="btn brand" onClick={save} disabled={!form.name}>Save connection</button>
        </div>
      </div>
    </>
  )
}

/* ---------------- Applications ---------------- */
function Applications() {
  const [data, setData] = useState(null)
  const [tenants, setTenants] = useState([])
  const [form, setForm] = useState({ tenant: 'acme', name: '', owner_team: '', oncall_email: '', criticality: 'medium', description: '', services: '' })
  const [msg, setMsg] = useState('')

  const load = async () => {
    setData(await api('/api/admin/applications'))
    setTenants((await api('/api/users')).tenants)
  }
  useEffect(() => { load() }, [])

  const save = async () => {
    const r = await post('/api/admin/applications', {
      ...form, services: form.services.split(',').map((s) => s.trim()).filter(Boolean),
    })
    setMsg(r.ok ? 'Application registered.' : r.error || 'Failed')
    load()
  }

  if (!data) return <div className="card spin">Loading…</div>
  return (
    <>
      <div className="card">
        <h2>Application catalog ({data.applications.length})</h2>
        <div className="cardsub">Every monitored application, its owning team, criticality and telemetry services — the backbone incident correlation and ownership routing run on.</div>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>Customer</th><th>Application</th><th>Owner team</th><th>On-call</th><th>Criticality</th><th>Services</th></tr></thead>
          <tbody>
            {data.applications.map((a) => (
              <tr key={a.id}>
                <td><span className="badge neutral">{a.tenant_name}</span></td>
                <td><b>{a.name}</b><div style={{ color: 'var(--muted)', fontSize: '.7rem' }}>{a.description}</div></td>
                <td>{a.owner_team}</td><td className="mono">{a.oncall_email}</td>
                <td><span className={`badge ${a.criticality === 'critical' ? 'sev1' : a.criticality === 'high' ? 'sev2' : 'neutral'}`}>{a.criticality}</span></td>
                <td className="mono">{(a.services || []).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      <div className="card">
        <h2>Register an application</h2>
        <div className="formrow">
          <div className="field"><label>Customer</label>
            <select value={form.tenant} onChange={(e) => setForm({ ...form, tenant: e.target.value })}>
              {tenants.map((t) => <option key={t.slug} value={t.slug}>{t.name}</option>)}
            </select></div>
          {[['name', 'Application name'], ['owner_team', 'Owner team'], ['oncall_email', 'On-call email']].map(([k, l]) => (
            <div className="field" key={k}><label>{l}</label>
              <input value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></div>
          ))}
          <div className="field"><label>Criticality</label>
            <select value={form.criticality} onChange={(e) => setForm({ ...form, criticality: e.target.value })}>
              {['critical', 'high', 'medium', 'low'].map((c) => <option key={c}>{c}</option>)}
            </select></div>
          <div className="field" style={{ gridColumn: 'span 2' }}><label>Telemetry service names (comma-separated)</label>
            <input value={form.services} placeholder="billing-api, billing-worker" onChange={(e) => setForm({ ...form, services: e.target.value })} /></div>
        </div>
        <button className="btn brand" onClick={save} disabled={!form.name}>Register application</button>
        <span style={{ marginLeft: '.6rem', color: 'var(--good)', fontSize: '.76rem' }}>{msg}</span>
      </div>
    </>
  )
}

/* ---------------- Users & Governance ---------------- */
function Governance() {
  const [users, setUsers] = useState([])
  const [usage, setUsage] = useState([])
  const [audit, setAudit] = useState([])
  const [tables, setTables] = useState([])

  useEffect(() => {
    api('/api/users').then((d) => setUsers(d.users))
    api('/api/admin/ai-usage').then((d) => setUsage(d.usage || []))
    api('/api/admin/audit-log').then((d) => setAudit(d.audit || []))
    api('/api/admin/db-stats').then((d) => setTables(d.tables || []))
  }, [])

  return (
    <>
      <div className="card">
        <h2>Users & roles</h2>
        <div className="cardsub">RBAC: admins configure, developers remediate, testers validate. Switch persona from the header to experience each role.</div>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>User</th><th>Email</th><th>Customer</th><th>Role</th><th>Permissions</th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.email}>
                <td><b>{u.display_name}</b></td><td className="mono">{u.email}</td>
                <td>{u.tenant_name}</td>
                <td><span className={`badge ${u.role === 'admin' ? 'brand' : u.role === 'developer' ? 'good' : 'neutral'}`}>{u.role}</span></td>
                <td className="mono" style={{ fontSize: '.66rem' }}>
                  {Object.entries(u.permissions).filter(([, v]) => v).map(([k]) => k).join(', ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      <div className="grid g2">
        <div className="card" style={{ marginBottom: 0 }}>
          <h2>AI usage (by provider)</h2>
          <div className="tablewrap"><table className="slds">
            <thead><tr><th>Provider</th><th>Calls</th><th>Avg latency</th><th>Chars in/out</th></tr></thead>
            <tbody>
              {usage.length === 0 && <tr><td colSpan="4" style={{ color: 'var(--muted)' }}>No AI calls yet.</td></tr>}
              {usage.map((u) => (
                <tr key={u.provider}>
                  <td><b>{u.provider}</b></td><td>{u.calls}</td>
                  <td>{u.avg_latency_ms} ms</td>
                  <td className="mono">{Number(u.prompt_chars).toLocaleString()} / {Number(u.completion_chars).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </div>
        <div className="card" style={{ marginBottom: 0 }}>
          <h2>PostgreSQL schema ({tables.length} tables)</h2>
          <div className="tablewrap" style={{ maxHeight: 260, overflowY: 'auto' }}><table className="slds">
            <thead><tr><th>Table</th><th>Rows</th></tr></thead>
            <tbody>
              {tables.map((t) => <tr key={t.table}><td className="mono">{t.table}</td><td>{Number(t.rows).toLocaleString()}</td></tr>)}
            </tbody>
          </table></div>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h2>Configuration audit log</h2>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>When</th><th>User</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead>
          <tbody>
            {audit.length === 0 && <tr><td colSpan="5" style={{ color: 'var(--muted)' }}>No configuration changes yet.</td></tr>}
            {audit.map((a, i) => (
              <tr key={i}>
                <td>{fmtAgo(a.ts)}</td><td className="mono">{a.user_email}</td>
                <td><span className="badge neutral">{a.action}</span></td><td className="mono">{a.entity}</td>
                <td className="mono" style={{ fontSize: '.66rem' }}>{JSON.stringify(a.detail)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>
    </>
  )
}

/* ---------------- Thresholds ---------------- */
function Thresholds() {
  const [cfg, setCfg] = useState(null)
  const [saved, setSaved] = useState('')
  const load = async () => setCfg(await api('/api/config'))
  useEffect(() => { load() }, [])

  const save = async (metric, warn, critical) => {
    await post('/api/config/threshold', { metric, warn: +warn, critical: +critical })
    setSaved(metric); setTimeout(() => setSaved(''), 1500)
  }

  if (!cfg) return <div className="card spin">Loading…</div>
  return (
    <div className="card">
      <h2>Alert thresholds</h2>
      <div className="cardsub">Warn and critical levels drive breach detection, incident severity and the predictive horizon. Stored in PostgreSQL — tune per client without code changes.</div>
      <div className="tablewrap"><table className="slds">
        <thead><tr><th>Metric</th><th>Warn</th><th>Critical</th><th></th></tr></thead>
        <tbody>
          {Object.entries(cfg.thresholds).map(([m, t]) => <ThresholdRow key={m} metric={m} t={t} onSave={save} saved={saved === m} />)}
        </tbody>
      </table></div>
    </div>
  )
}

function ThresholdRow({ metric, t, onSave, saved }) {
  const [warn, setWarn] = useState(t.warn)
  const [critical, setCritical] = useState(t.critical)
  return (
    <tr>
      <td className="mono">{metric}</td>
      <td><input style={{ width: 90 }} type="number" value={warn} onChange={(e) => setWarn(e.target.value)} /></td>
      <td><input style={{ width: 90 }} type="number" value={critical} onChange={(e) => setCritical(e.target.value)} /></td>
      <td><button className="btn sm" onClick={() => onSave(metric, warn, critical)}>Save</button>
        {saved && <span style={{ color: 'var(--good)', marginLeft: 8 }}>✓</span>}</td>
    </tr>
  )
}
