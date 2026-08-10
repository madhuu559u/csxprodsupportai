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

/* ---------------- Applications + onboarding wizard ---------------- */
function Applications() {
  const [data, setData] = useState(null)
  const [tenants, setTenants] = useState([])
  const [wizard, setWizard] = useState(false)
  const [detail, setDetail] = useState(null)

  const load = async () => {
    setData(await api('/api/admin/applications'))
    setTenants((await api('/api/users')).tenants)
  }
  useEffect(() => { load() }, [])

  const openDetail = async (id) => setDetail(await api(`/api/admin/applications/${id}/detail`))

  if (!data) return <div className="card spin">Loading…</div>
  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>Application catalog ({data.applications.length})</h2>
          <button className="btn brand" style={{ marginLeft: 'auto' }} onClick={() => setWizard(true)}>＋ Onboard application</button>
        </div>
        <div className="cardsub" style={{ marginTop: '.4rem' }}>Click a row to see everything collected at onboarding — services, watch patterns, SOPs, databases, dependencies. The platform acts on all of it.</div>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>Customer</th><th>Application</th><th>Owner team</th><th>Criticality</th><th>Services</th><th>Patterns</th><th>SOPs</th></tr></thead>
          <tbody>
            {data.applications.map((a) => (
              <tr key={a.id} style={{ cursor: 'pointer' }} onClick={() => openDetail(a.id)}>
                <td><span className="badge neutral">{a.tenant_name}</span></td>
                <td><b>{a.name}</b><div style={{ color: 'var(--muted)', fontSize: '.7rem' }}>{a.description}</div></td>
                <td>{a.owner_team}</td>
                <td><span className={`badge ${a.criticality === 'critical' ? 'sev1' : a.criticality === 'high' ? 'sev2' : 'neutral'}`}>{a.criticality}</span></td>
                <td className="mono">{(a.services || []).join(', ')}</td>
                <td>{a.pattern_count > 0 ? <span className="badge brand">{a.pattern_count}</span> : '—'}</td>
                <td>{a.sop_count > 0 ? <span className="badge good">{a.sop_count}</span> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      {detail && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <h2 style={{ margin: 0 }}>{detail.name} <span className="badge neutral">{detail.tenant_name}</span></h2>
            <button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => setDetail(null)}>Close</button>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: '.78rem' }}>{detail.description}</p>
          <div className="grid g2">
            <div>
              <h2 style={{ fontSize: '.8rem' }}>Profile</h2>
              <table className="slds"><tbody>
                <tr><td>Business impact</td><td>{detail.profile?.business_impact || '—'}</td></tr>
                <tr><td>SLA target</td><td>{detail.profile?.sla_target || '—'}</td></tr>
                <tr><td>Environment</td><td>{detail.profile?.environment || '—'}</td></tr>
                <tr><td>Log locations</td><td className="mono">{(detail.profile?.log_locations || []).join(', ') || '—'}</td></tr>
                <tr><td>Upstream deps</td><td className="mono">{(detail.profile?.dependencies?.upstream || []).join(', ') || '—'}</td></tr>
                <tr><td>Downstream deps</td><td className="mono">{(detail.profile?.dependencies?.downstream || []).join(', ') || '—'}</td></tr>
              </tbody></table>
            </div>
            <div>
              <h2 style={{ fontSize: '.8rem' }}>Watch patterns ({detail.patterns.length})</h2>
              {detail.patterns.map((p) => (
                <div key={p.id} className={`evd ${p.severity === 'critical' ? 'metric' : 'log'}`}>
                  <b>{p.name}</b> <span className="badge neutral">{p.severity}</span>
                  <div className="mono" style={{ fontSize: '.68rem' }}>{p.pattern}</div>
                  <div style={{ color: 'var(--muted)', fontSize: '.7rem' }}>{p.description}</div>
                </div>
              ))}
              {detail.patterns.length === 0 && <div style={{ color: 'var(--muted)', fontSize: '.75rem' }}>None configured.</div>}
            </div>
          </div>
          <h2 style={{ fontSize: '.8rem' }}>Standard operating procedures ({detail.sops.length})</h2>
          {detail.sops.map((s) => (
            <details key={s.id} style={{ margin: '.3rem 0' }}>
              <summary>{s.title} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>— when: {s.trigger_hint}</span></summary>
              <pre className="mono" style={{ background: '#fafaf9', padding: '.6rem', borderRadius: '.35rem', whiteSpace: 'pre-wrap', fontSize: '.72rem' }}>{s.content}</pre>
            </details>
          ))}
          {detail.sops.length === 0 && <div style={{ color: 'var(--muted)', fontSize: '.75rem' }}>None configured.</div>}
        </div>
      )}

      {wizard && <OnboardWizard tenants={tenants} onClose={() => { setWizard(false); load() }} />}
    </>
  )
}

const EMPTY_ONBOARD = {
  tenant: 'acme', name: '', description: '', owner_team: '', oncall_email: '',
  criticality: 'medium', business_impact: '', sla_target: '99.9% monthly', environment: 'production',
  services: '', dependencies_upstream: '', dependencies_downstream: '',
  log_locations: '', log_sample_text: '', log_sample_url: '',
  patterns: [], databases: [], sops: [],
}

function OnboardWizard({ tenants, onClose }) {
  const [step, setStep] = useState(0)
  const [f, setF] = useState({ ...EMPTY_ONBOARD, tenant: tenants[0]?.slug || 'acme' })
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }))
  const csv = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)

  const STEPS = ['Basics', 'Telemetry & logs', 'Watch patterns', 'Databases', 'SOPs & dependencies', 'Review & launch']

  const submit = async () => {
    setBusy(true)
    const r = await post('/api/admin/applications/onboard', {
      ...f,
      services: csv(f.services),
      log_locations: csv(f.log_locations),
      dependencies_upstream: csv(f.dependencies_upstream),
      dependencies_downstream: csv(f.dependencies_downstream),
      log_sample_text: f.log_sample_text || null,
      log_sample_url: f.log_sample_url || null,
    })
    setBusy(false)
    setResult(r)
  }

  const addRow = (key, row) => set(key, [...f[key], row])
  const dropRow = (key, i) => set(key, f[key].filter((_, k) => k !== i))

  return (
    <div className="modalbg" onClick={(e) => e.target.className === 'modalbg' && onClose()}>
      <div className="modal" style={{ width: 720, maxHeight: '90vh', overflowY: 'auto' }}>
        <div className="mhead">Onboard a new application</div>
        <div className="mbody">
          <div className="pathbar">
            {STEPS.map((s, i) => (
              <div key={s} className={`step ${i < step ? 'done' : ''} ${i === step ? 'now' : ''}`}
                style={{ cursor: 'pointer' }} onClick={() => !result && setStep(i)}>{s}</div>
            ))}
          </div>

          {result ? (
            result.ok ? (
              <div className="evd good">
                ✅ <b>{f.name}</b> onboarded. {result.summary.services.length} service(s), {result.summary.patterns} watch
                pattern(s) now actively scanning logs, {result.summary.sops} SOP(s) attached to incidents & copilot,{' '}
                {result.summary.databases} database(s) registered for pool monitoring, {result.summary.log_lines_ingested} log
                lines ingested & clustered.
              </div>
            ) : <div className="evd metric">⛔ {result.error}</div>
          ) : (
            <>
              {step === 0 && (
                <div className="formrow">
                  <div className="field"><label>Customer</label>
                    <select value={f.tenant} onChange={(e) => set('tenant', e.target.value)}>
                      {tenants.map((t) => <option key={t.slug} value={t.slug}>{t.name}</option>)}
                    </select></div>
                  <div className="field"><label>Application name *</label>
                    <input value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="Billing" /></div>
                  <div className="field"><label>Owner team</label>
                    <input value={f.owner_team} onChange={(e) => set('owner_team', e.target.value)} /></div>
                  <div className="field"><label>On-call email</label>
                    <input value={f.oncall_email} onChange={(e) => set('oncall_email', e.target.value)} /></div>
                  <div className="field"><label>Criticality</label>
                    <select value={f.criticality} onChange={(e) => set('criticality', e.target.value)}>
                      {['critical', 'high', 'medium', 'low'].map((c) => <option key={c}>{c}</option>)}
                    </select></div>
                  <div className="field"><label>Environment</label>
                    <select value={f.environment} onChange={(e) => set('environment', e.target.value)}>
                      {['production', 'staging', 'uat', 'dev'].map((c) => <option key={c}>{c}</option>)}
                    </select></div>
                  <div className="field" style={{ gridColumn: 'span 2' }}><label>What does this application do?</label>
                    <input value={f.description} onChange={(e) => set('description', e.target.value)}
                      placeholder="Invoicing, settlement and dunning for all B2B accounts" /></div>
                  <div className="field"><label>Business impact if down</label>
                    <input value={f.business_impact} onChange={(e) => set('business_impact', e.target.value)}
                      placeholder="Revenue collection halts; finance close at risk" /></div>
                  <div className="field"><label>SLA target</label>
                    <input value={f.sla_target} onChange={(e) => set('sla_target', e.target.value)} /></div>
                </div>
              )}

              {step === 1 && (
                <>
                  <div className="field"><label>Telemetry service names (comma-separated) — how this app appears in logs/metrics</label>
                    <input value={f.services} onChange={(e) => set('services', e.target.value)} placeholder="billing-api, billing-worker" /></div>
                  <div className="field"><label>Log locations (paths, index names, URLs — comma-separated)</label>
                    <input value={f.log_locations} onChange={(e) => set('log_locations', e.target.value)}
                      placeholder="/var/log/billing/*.log, splunk:index=billing_prod" /></div>
                  <div className="field"><label>Bootstrap log sample — paste raw lines (optional)</label>
                    <textarea value={f.log_sample_text} onChange={(e) => set('log_sample_text', e.target.value)}
                      placeholder="2026-08-09 11:02:11 ERROR [billing-api] ..." /></div>
                  <div className="field"><label>…or fetch a log file from a URL (optional)</label>
                    <input value={f.log_sample_url} onChange={(e) => set('log_sample_url', e.target.value)}
                      placeholder="https://raw.githubusercontent.com/.../app.log" /></div>
                </>
              )}

              {step === 2 && (
                <RowEditor
                  title="Watch patterns — the platform scans every ingested log line for these and raises anomalies"
                  rows={f.patterns} onDrop={(i) => dropRow('patterns', i)}
                  render={(p) => <><b>{p.name}</b> <span className="badge neutral">{p.severity}</span> <span className="mono">{p.pattern}</span></>}
                  fields={[['name', 'Pattern name', 'Payment gateway 5xx'], ['pattern', 'Regex / substring', 'Gateway returned 5\\d\\d'],
                           ['severity', 'Severity', 'error'], ['description', 'Description', 'PSP outage indicator']]}
                  selects={{ severity: ['critical', 'error', 'warn', 'info'] }}
                  onAdd={(row) => addRow('patterns', row)} />
              )}

              {step === 3 && (
                <RowEditor
                  title="Databases behind this application — registered for connectivity + pool monitoring"
                  rows={f.databases} onDrop={(i) => dropRow('databases', i)}
                  render={(d) => <><b>{d.name}</b> <span className="mono">{d.engine}://{d.host}:{d.port}/{d.dbname}</span> pool {d.pool_min}–{d.pool_max}</>}
                  fields={[['name', 'Name', 'Billing PostgreSQL'], ['engine', 'Engine', 'postgresql'], ['host', 'Host', 'db.internal'],
                           ['port', 'Port', '5432'], ['dbname', 'Database', 'billing'], ['username', 'Username', 'svc_billing'],
                           ['password', 'Password', ''], ['pool_min', 'Pool min', '2'], ['pool_max', 'Pool max', '20']]}
                  selects={{ engine: ['postgresql', 'mysql', 'oracle', 'sqlserver'] }}
                  numeric={['port', 'pool_min', 'pool_max']}
                  onAdd={(row) => addRow('databases', row)} />
              )}

              {step === 4 && (
                <>
                  <RowEditor
                    title="SOPs — standard operating procedures shown on matching incidents and used by the copilot"
                    rows={f.sops} onDrop={(i) => dropRow('sops', i)}
                    render={(s) => <><b>{s.title}</b> <span style={{ color: 'var(--muted)' }}>when: {s.trigger_hint}</span></>}
                    fields={[['title', 'SOP title', 'SOP: Billing DB failover'], ['trigger_hint', 'When to use', 'Primary DB unreachable'],
                             ['content', 'Steps (multiline)', '1. Verify replica lag...\n2. Promote replica...']]}
                    textareas={['content']}
                    onAdd={(row) => addRow('sops', row)} />
                  <div className="formrow" style={{ marginTop: '.6rem' }}>
                    <div className="field"><label>Upstream dependencies (callers)</label>
                      <input value={f.dependencies_upstream} onChange={(e) => set('dependencies_upstream', e.target.value)} placeholder="web-gateway" /></div>
                    <div className="field"><label>Downstream dependencies (called systems)</label>
                      <input value={f.dependencies_downstream} onChange={(e) => set('dependencies_downstream', e.target.value)} placeholder="postgres-billing, kafka, psp-gateway" /></div>
                  </div>
                </>
              )}

              {step === 5 && (
                <div style={{ fontSize: '.8rem' }}>
                  <div className="evd good"><b>{f.name || '(unnamed)'}</b> → {tenants.find((t) => t.slug === f.tenant)?.name} · {f.criticality} · {f.environment}</div>
                  <div className="evd">Services: <span className="mono">{f.services || '(auto from name)'}</span></div>
                  <div className="evd">Log locations: <span className="mono">{f.log_locations || '—'}</span> · sample: {f.log_sample_url ? 'URL fetch' : f.log_sample_text ? `${f.log_sample_text.split('\n').length} pasted lines` : 'none'}</div>
                  <div className="evd">Watch patterns: {f.patterns.length} · Databases: {f.databases.length} · SOPs: {f.sops.length}</div>
                  <div className="evd">Dependencies: ↑ {f.dependencies_upstream || '—'} · ↓ {f.dependencies_downstream || '—'}</div>
                  <p style={{ color: 'var(--muted)' }}>On launch: the application is registered, patterns begin scanning all ingested logs,
                    SOPs attach to matching incidents, databases are registered for pool monitoring, and the log sample is ingested & clustered.</p>
                </div>
              )}
            </>
          )}
        </div>
        <div className="mfoot">
          <button className="btn" onClick={onClose}>{result ? 'Done' : 'Cancel'}</button>
          {!result && step > 0 && <button className="btn" onClick={() => setStep(step - 1)}>Back</button>}
          {!result && step < 5 && <button className="btn brand" onClick={() => setStep(step + 1)} disabled={step === 0 && !f.name}>Next</button>}
          {!result && step === 5 && <button className="btn brand" onClick={submit} disabled={busy || !f.name}>{busy ? 'Onboarding…' : '🚀 Launch onboarding'}</button>}
        </div>
      </div>
    </div>
  )
}

function RowEditor({ title, rows, render, fields, selects = {}, textareas = [], numeric = [], onAdd, onDrop }) {
  const empty = Object.fromEntries(fields.map(([k]) => [k, selects[k] ? selects[k][0] : '']))
  const [draft, setDraft] = useState(empty)
  return (
    <div>
      <div style={{ fontSize: '.78rem', fontWeight: 700, marginBottom: '.4rem' }}>{title}</div>
      {rows.map((r, i) => (
        <div key={i} className="evd" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
          <span style={{ flex: 1 }}>{render(r)}</span>
          <button className="btn sm danger" onClick={() => onDrop(i)}>✕</button>
        </div>
      ))}
      <div className="formrow" style={{ marginTop: '.5rem' }}>
        {fields.map(([k, label, ph]) => (
          <div className="field" key={k} style={textareas.includes(k) ? { gridColumn: 'span 3' } : {}}>
            <label>{label}</label>
            {selects[k] ? (
              <select value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}>
                {selects[k].map((o) => <option key={o}>{o}</option>)}
              </select>
            ) : textareas.includes(k) ? (
              <textarea value={draft[k]} placeholder={ph} style={{ minHeight: 70 }}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
            ) : (
              <input value={draft[k]} placeholder={ph} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
            )}
          </div>
        ))}
      </div>
      <button className="btn sm" onClick={() => {
        if (!draft[fields[0][0]]) return
        const row = { ...draft }
        numeric.forEach((k) => { row[k] = +row[k] || 0 })
        onAdd(row); setDraft(empty)
      }}>＋ Add</button>
    </div>
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
