import { useEffect, useState } from 'react'
import { api, post, PROVIDER_LABEL, getToken, clearAuth, currentTenant, setCurrentTenant } from './api'
import Login from './pages/Login'
import Home from './pages/Home'
import Incidents from './pages/Incidents'
import Logs from './pages/Logs'
import Predictions from './pages/Predictions'
import Runbooks from './pages/Runbooks'
import Copilot from './pages/Copilot'
import Admin from './pages/Admin'

const TABS = [
  ['home', 'Home'], ['incidents', 'Incident Command'], ['logs', 'Log Intelligence'],
  ['predict', 'Predictive Alerts'], ['runbooks', 'Runbooks'], ['copilot', 'Copilot'], ['admin', 'Administration'],
]

export default function App() {
  const [tab, setTab] = useState('home')
  const [ai, setAi] = useState(null)
  const [me, setMe] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [tenants, setTenants] = useState([])
  const [tenantSel, setTenantSel] = useState(currentTenant())
  const [approval, setApproval] = useState(null)
  const [approver, setApprover] = useState('')
  const [approvalResult, setApprovalResult] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  // session bootstrap
  useEffect(() => {
    if (!getToken()) { setAuthChecked(true); return }
    api('/api/whoami').then((u) => {
      if (u.email) setMe(u); else clearAuth()
      setAuthChecked(true)
    }).catch(() => { clearAuth(); setAuthChecked(true) })
  }, [])

  useEffect(() => {
    if (!me) return
    api('/api/users').then((d) => setTenants(d.tenants || []))
    const load = () => api('/api/overview').then((o) => setAi(o.ai)).catch(() => {})
    load(); const t = setInterval(load, 30000); return () => clearInterval(t)
  }, [tab, refreshKey, me])

  const logout = async () => { await post('/api/auth/logout'); clearAuth(); setMe(null) }
  const switchTenant = (slug) => { setCurrentTenant(slug); setTenantSel(slug); setRefreshKey((k) => k + 1) }

  if (!authChecked) return null
  if (!me) return <Login onLogin={(u) => { setMe(u); setTenantSel(u.tenant || '') }} />

  const canAdmin = me.permissions?.admin_config
  const onApprove = (rbId, after) => { setApproval({ rbId, after }); setApprovalResult(null) }
  const confirmApproval = async () => {
    const r = await post(`/api/runbooks/${approval.rbId}/execute`, { approved_by: approver || me.display_name })
    setApprovalResult(r)
    approval.after?.()
  }

  const aiLive = ai && ai.mode !== 'offline'
  return (
    <>
      <header className="gheader">
        <div className="glogo"><div className="cloud">⚡</div>NEXUS <span style={{ color: 'var(--brand)' }}>OpsAI</span></div>
        <div className="gsearch"><input placeholder="Search incidents, services, runbooks…" /></div>
        <div className="gright">
          {canAdmin ? (
            <select value={tenantSel} onChange={(e) => switchTenant(e.target.value)}
              style={{ border: '1px solid var(--border-strong)', borderRadius: '.35rem', padding: '.3rem .4rem', font: 'inherit' }}>
              <option value="">All customers</option>
              {tenants.map((t) => <option key={t.slug} value={t.slug}>{t.name}</option>)}
            </select>
          ) : (
            <span className="badge neutral">{me.tenant_name}</span>
          )}
          <span className="aibadge">
            <span className="dot" style={{ background: aiLive ? 'var(--good)' : 'var(--warn)' }} />
            {ai ? (aiLive ? `AI: ${PROVIDER_LABEL[ai.mode]} (${ai.model})` : 'AI: offline engine') : '…'}
          </span>
          <span className="aibadge" title={me.email}>
            👤 {me.display_name} <span className="badge brand" style={{ marginLeft: 4 }}>{me.role}</span>
          </span>
          {canAdmin && <button className="btn sm" onClick={async () => { await post('/api/demo/reset'); location.reload() }}>Reset demo</button>}
          <button className="btn sm" onClick={logout}>Sign out</button>
        </div>
      </header>

      <nav className="appnav">
        <div className="appname">Operations Cloud</div>
        {TABS.filter(([k]) => k !== 'admin' || canAdmin).map(([k, label]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{label}</button>
        ))}
      </nav>

      <div key={refreshKey}>
        {tab === 'home' && <Home />}
        {tab === 'incidents' && <Incidents onApprove={onApprove} me={me} />}
        {tab === 'logs' && <Logs />}
        {tab === 'predict' && <Predictions />}
        {tab === 'runbooks' && <Runbooks onApprove={onApprove} me={me} />}
        {tab === 'copilot' && <Copilot />}
        {tab === 'admin' && canAdmin && <Admin />}
      </div>

      {approval && (
        <div className="modalbg" onClick={(e) => e.target.className === 'modalbg' && setApproval(null)}>
          <div className="modal">
            <div className="mhead">Human approval required</div>
            <div className="mbody">
              {!approvalResult ? (
                <>
                  <p style={{ marginTop: 0, color: 'var(--ink-2)', fontSize: '.8rem' }}>
                    Runbook <code className="mono">{approval.rbId}</code> is <b>tier 2</b> — a state-changing action
                    that requires human sign-off. Your identity ({me.email}) and approval are recorded in the
                    immutable audit trail.
                  </p>
                  <div className="field"><label>Approval note / name</label>
                    <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder={me.display_name} /></div>
                </>
              ) : approvalResult.ok ? (
                <div className="evd good">✅ Executed (id {approvalResult.execution_id}) — verification{' '}
                  <b>{approvalResult.verification.status}</b>: {approvalResult.verification.detail}</div>
              ) : (
                <div className="evd metric">⛔ {approvalResult.error}</div>
              )}
            </div>
            <div className="mfoot">
              <button className="btn" onClick={() => setApproval(null)}>{approvalResult ? 'Close' : 'Cancel'}</button>
              {!approvalResult && <button className="btn brand" onClick={confirmApproval}>Approve & execute</button>}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
