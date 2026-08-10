import { useEffect, useState } from 'react'
import { api, post, fmtAgo } from '../api'
import { PageHead } from '../bits'

const TIER_INFO = {
  0: ['observe', 'neutral'], 1: ['recommend', 'neutral'], 2: ['approval required', 'sev3'],
  3: ['auto-heal', 'good'], 4: ['restricted', 'sev1'],
}

export default function Runbooks({ onApprove, me }) {
  const canExec = !me || me.permissions?.execute_runbooks
  const [d, setD] = useState(null)
  const [results, setResults] = useState({})

  const load = async () => setD(await api('/api/runbooks'))
  useEffect(() => { load() }, [])

  const exec = async (rb) => {
    if (rb.tier === 2) { onApprove(rb.id, load); return }
    const r = await post(`/api/runbooks/${rb.id}/execute`, {})
    setResults((x) => ({ ...x, [rb.id]: r }))
    load()
  }

  if (!d) return <div className="page"><div className="card spin">Loading catalog…</div></div>
  return (
    <div className="page">
      <PageHead icon="🛠" tint="linear-gradient(135deg,#1baf7a,#04844b)" crumb="Operations Cloud"
        title="Runbooks & Self-Healing"
        desc="AI proposes · policy decides · automation executes · humans keep authority on risk. Every run is verified against telemetry and audited in PostgreSQL." />

      <div className="grid g3">
        {d.runbooks.map((r) => {
          const [tname, tclass] = TIER_INFO[r.tier]
          const res = results[r.id]
          return (
            <div className="card" key={r.id} style={{ marginBottom: 0 }}>
              <div style={{ fontWeight: 700 }}>{r.name} <span className={`badge ${tclass}`}>tier {r.tier} · {tname}</span></div>
              <div className="mono" style={{ color: 'var(--muted)', margin: '.2rem 0' }}>{r.id}</div>
              <div style={{ fontSize: '.74rem', color: 'var(--muted)' }}>match: {r.match.service} · {r.match.signals.join(', ')}</div>
              <ul style={{ fontSize: '.76rem', paddingLeft: '1.2rem', margin: '.5rem 0' }}>
                {r.steps.map((s, i) => <li key={i}><code className="mono">{s.action}</code> — {s.detail}</li>)}
              </ul>
              <div style={{ fontSize: '.72rem', color: 'var(--muted)' }}>verify: {r.verify ? r.verify.expected : '—'}</div>
              <div style={{ marginTop: '.6rem' }}>
                {r.tier >= 4
                  ? <span className="badge sev1">restricted — change management only</span>
                  : !canExec
                  ? <span className="badge neutral" title="Your role is read/validate only">role '{me?.role}' cannot execute — view only</span>
                  : <button className={`btn ${r.tier === 3 ? 'brand' : ''}`} onClick={() => exec(r)}>
                      {r.tier === 2 ? 'Request execution (approval)' : 'Auto-heal now'}
                    </button>}
              </div>
              {res && (
                <div className={`evd ${res.ok ? 'good' : 'metric'}`} style={{ marginTop: '.5rem' }}>
                  {res.ok
                    ? <>✅ Executed (id {res.execution_id}) — verification <b>{res.verification.status}</b>: {res.verification.detail}</>
                    : <>⛔ {res.error}</>}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <h2>Audit trail (PostgreSQL — immutable)</h2>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>When</th><th>Runbook</th><th>Tier</th><th>Outcome</th><th>Approved by</th><th>Verification</th></tr></thead>
          <tbody>
            {d.audit.length === 0 && <tr><td colSpan="6" style={{ color: 'var(--muted)' }}>No automation runs yet.</td></tr>}
            {d.audit.map((a) => (
              <tr key={a.id}>
                <td>{fmtAgo(a.ts)}</td>
                <td className="mono">{a.runbook}</td>
                <td>{a.tier}</td>
                <td>{a.outcome === 'executed' ? <span className="badge good">executed</span> : <span className="badge sev1">{a.outcome}</span>}</td>
                <td>{a.approved_by || '—'}</td>
                <td>{a.verification ? a.verification.status : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>
    </div>
  )
}
