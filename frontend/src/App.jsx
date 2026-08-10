import { useEffect, useState } from 'react'
import { api, post, PROVIDER_LABEL, currentUserEmail, setCurrentUser, currentTenant, setCurrentTenant } from './api'
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
  const [directory, setDirectory] = useState({ users: [], tenants: [] })
  const [tenantSel, setTenantSel] = useState(currentTenant())
  const [approval, setApproval] = useState(null)
  const [approver, setApprover] = useState('')
  const [approvalResult, setApprovalResult] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => { api('/api/users').then(setDirectory) }, [])
  useEffect(() => {
    api('/api/whoami').then(setMe).catch(() => {})
    const load = () => api('/api/overview').then((o) => setAi(o.ai)).catch(() => {})
    load(); const t = setInterval(load, 30000); return () => clearInterval(t)
  }, [tab, refreshKey])

  const switchUser = (email) => {
    setCurrentUser(email)
    // auto-scope to the persona's own tenant for a realistic customer experience
    const u = directory.users.find((x) => x.email === email)
    if (u) { setCurrentTenant(u.tenant); setTenantSel(u.tenant) }
    setRefreshKey((k) => k + 1)
    setTab('home')
  }
  const switchTenant = (slug) => { setCurrentTenant(slug); setTenantSel(slug); setRefreshKey((k) => k + 1) }

  const canAdmin = !me || me.permissions?.admin_config
  const onApprove = (rbId, after) => { setApproval({ rbId, after }); setApprovalResult(null) }
  const confirmApproval = async () => {
    const r = await post(`/api/runbooks/${approval.rbId}/execute`, { approved_by: approver || me?.display_name || 'operator' })
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
          <select value={tenantSel} onChange={(e) => switchTenant(e.target.value)}
            style={{ border: '1px solid var(--border-strong)', borderRadius: '.35rem', padding: '.3rem .4rem', font: 'inherit' }}>
            <option value="">All customers</option>
            {directory.tenants.map((t) => <option key={t.slug} value={t.slug}>{t.name}</option>)}
          </select>
          <select value={currentUserEmail()} onChange={(e) => switchUser(e.target.value)}
            style={{ border: '1px solid var(--border-strong)', borderRadius: '.35rem', padding: '.3rem .4rem', font: 'inherit', maxWidth: 210 }}>
            <option value="">Platform Bootstrap (admin)</option>
            {directory.users.map((u) => (
              <option key={u.email} value={u.email}>{u.display_name} — {u.role} @ {u.tenant}</option>
            ))}
          </select>
          {me && <span className="badge brand">{me.role}</span>}
          <span className="aibadge">
            <span className="dot" style={{ background: aiLive ? 'var(--good)' : 'var(--warn)' }} />
            {ai ? (aiLive ? `AI: ${PROVIDER_LABEL[ai.mode]} (${ai.model})` : 'AI: offline engine') : '…'}
          </span>
          <button className="btn sm" onClick={async () => { await post('/api/demo/reset'); location.reload() }}>Reset demo</button>
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
                    that requires human sign-off. Your identity ({me?.email || 'platform admin'}) and approval are
                    recorded in the immutable audit trail.
                  </p>
                  <div className="field"><label>Approval note / name</label>
                    <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder={me?.display_name || 'jane.doe'} /></div>
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
