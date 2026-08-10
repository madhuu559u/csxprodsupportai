import { useEffect, useState } from 'react'
import { api, post, fmtAgo, withTenant } from '../api'
import { PageHead, Md, ModeTag, SevBadge } from '../bits'

export default function Incidents({ onApprove }) {
  const [incs, setIncs] = useState(null)
  const [panels, setPanels] = useState({})   // { [id]: {brief, rca, runbooks, busy} }

  const load = async () => setIncs((await api(withTenant('/api/incidents'))).incidents)
  useEffect(() => { load() }, [])

  const setPanel = (id, patch) => setPanels((p) => ({ ...p, [id]: { ...(p[id] || {}), ...patch } }))

  const brief = async (id) => {
    setPanel(id, { busy: 'AI is analyzing evidence…' })
    const r = await post(`/api/incidents/${id}/brief`)
    setPanel(id, { busy: null, brief: r })
  }
  const rca = async (id) => {
    setPanel(id, { busy: 'Generating evidence-bounded RCA…' })
    const r = await post(`/api/incidents/${id}/rca`)
    setPanel(id, { busy: null, rca: r })
  }
  const runbooks = async (id) => {
    const inc = await api(`/api/incidents/${id}`)
    setPanel(id, { runbooks: inc.recommended_runbooks || [], sops: inc.sops || [] })
  }
  const exec = async (rbId, tier, incId) => {
    if (tier === 2) { onApprove(rbId, () => { load(); runbooks(incId) }); return }
    const r = await post(`/api/runbooks/${rbId}/execute`, {})
    setPanel(incId, { execResult: r })
    load()
  }

  if (!incs) return <div className="page"><div className="card spin">Correlating signals…</div></div>
  return (
    <div className="page">
      <PageHead icon="🚨" tint="linear-gradient(135deg,#ba0517,#ff5d2d)" crumb="Operations Cloud"
        title="Incident Command"
        desc="Signals across metrics, logs and forecasts are correlated automatically — with evidence, blast radius and change suspects."
        actions={<button className="btn" onClick={load}>Refresh</button>} />

      {incs.length === 0 && <div className="card">No active or predicted incidents 🎉</div>}
      {incs.map((i) => {
        const p = panels[i.id] || {}
        const stage = i.status === 'predicted' ? 0 : 1
        return (
          <div className="card" key={i.id}>
            <div style={{ display: 'flex', gap: '.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <SevBadge sev={i.severity} />
              <b>{i.id}</b><span style={{ color: 'var(--ink-2)' }}>{i.title}</span>
              <span className="badge neutral">{i.status}</span>
              <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: '.75rem' }}>owner: {i.owner}</span>
            </div>
            <div className="pathbar">
              {['Detected', 'Triaged', 'Remediating', 'Verified', 'RCA & Learn'].map((s, idx) => (
                <div key={s} className={`step ${idx < stage + 1 ? 'done' : ''} ${idx === stage + 1 ? 'now' : ''}`}>{s}</div>
              ))}
            </div>
            <div style={{ fontSize: '.76rem', color: 'var(--muted)' }}>
              signals: {i.signals.map((s) => <code key={s} className="mono" style={{ marginRight: 6 }}>{s}</code>)}
              &nbsp;·&nbsp; blast radius — upstream: {i.blast_radius.upstream.join(', ') || '—'} · downstream: {i.blast_radius.downstream.join(', ') || '—'}
            </div>
            {i.changes.length > 0 && (
              <div className="evd prediction" style={{ marginTop: '.5rem' }}>
                ⚠ <b>Change suspect:</b> {i.changes[0].detail} <i>({fmtAgo(i.changes[0].ts)})</i>
              </div>
            )}
            <details style={{ marginTop: '.5rem' }}>
              <summary>Evidence ({i.evidence.length})</summary>
              {i.evidence.map((e, k) => <div key={k} className={`evd ${e.type}`}>[{e.type}] {e.detail}</div>)}
            </details>
            <div style={{ marginTop: '.7rem', display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
              <button className="btn brand" onClick={() => brief(i.id)}>⚡ AI incident brief</button>
              <button className="btn" onClick={() => rca(i.id)}>📄 Generate RCA draft</button>
              <button className="btn" onClick={() => runbooks(i.id)}>🛠 Recommended runbooks</button>
            </div>
            {p.busy && <div className="spin" style={{ marginTop: '.5rem' }}>{p.busy}</div>}
            {p.brief && <div style={{ marginTop: '.6rem' }}><Md text={p.brief.brief} /><ModeTag mode={p.brief.mode} /></div>}
            {p.runbooks && (
              <div style={{ marginTop: '.5rem' }}>
                {p.runbooks.length === 0 && <div className="evd">No matching runbook — escalate to L2.</div>}
                {p.runbooks.map((r) => (
                  <div key={r.id} className="evd good">
                    <b>{r.name}</b> <span className="badge neutral">tier {r.tier}</span>{' '}
                    <span className="mono" style={{ color: 'var(--muted)' }}>{r.id}</span>{' '}
                    <button className="btn sm" onClick={() => exec(r.id, r.tier, i.id)}>Execute</button>
                  </div>
                ))}
              </div>
            )}
            {p.sops && p.sops.length > 0 && (
              <div style={{ marginTop: '.4rem' }}>
                {p.sops.map((s) => (
                  <details key={s.id} className="evd" style={{ borderColor: 'var(--s1)' }}>
                    <summary>📘 {s.title} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>— when: {s.trigger_hint}</span></summary>
                    <pre className="mono" style={{ whiteSpace: 'pre-wrap', fontSize: '.7rem', margin: '.3rem 0 0' }}>{s.content}</pre>
                  </details>
                ))}
              </div>
            )}
            {p.execResult && (
              <div className={`evd ${p.execResult.ok ? 'good' : 'metric'}`} style={{ marginTop: '.4rem' }}>
                {p.execResult.ok
                  ? <>✅ Executed — verification: <b>{p.execResult.verification.status}</b></>
                  : <>⛔ {p.execResult.error}</>}
              </div>
            )}
            {p.rca && (
              <div className="card" style={{ marginTop: '.6rem', background: '#fafaf9' }}>
                <Md text={p.rca.rca} /><ModeTag mode={p.rca.mode} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
