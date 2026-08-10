import { useEffect, useState } from 'react'
import { post, api, setToken, setCurrentTenant } from '../api'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [personas, setPersonas] = useState([])
  const [hint, setHint] = useState('')

  useEffect(() => {
    api('/api/auth/demo-credentials').then((d) => { setPersonas(d.personas || []); setHint(d.password_hint) })
  }, [])

  const submit = async (e, presetEmail) => {
    e?.preventDefault()
    const em = presetEmail || email
    const pw = presetEmail ? hint : password
    if (!em || !pw) { setError('Enter email and password.'); return }
    setBusy(true); setError('')
    const r = await post('/api/auth/login', { email: em, password: pw })
    setBusy(false)
    if (r.token) {
      setToken(r.token)
      setCurrentTenant(r.user.tenant || '')
      onLogin(r.user)
    } else {
      setError(r.error || 'Invalid email or password.')
    }
  }

  const roleColor = { admin: 'brand', developer: 'good', tester: 'neutral' }
  return (
    <div style={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
      {/* brand panel */}
      <div style={{ background: 'linear-gradient(160deg,#032d60,#0176d3 70%,#1b96ff)', color: '#fff',
        display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '4rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: '1.6rem', fontWeight: 800 }}>
          <div className="cloud" style={{ width: 46, height: 46, borderRadius: 10, background: 'rgba(255,255,255,.18)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>⚡</div>
          NEXUS OpsAI
        </div>
        <p style={{ fontSize: '1.05rem', opacity: 0.92, maxWidth: 460, lineHeight: 1.6, marginTop: '1rem' }}>
          The AI-native production support platform: detects, explains, predicts, resolves and learns —
          on top of the observability stack you already own.
        </p>
        <ul style={{ opacity: 0.85, lineHeight: 2, fontSize: '.85rem', paddingLeft: '1.2rem' }}>
          <li>Log pattern mining with client-configured watch patterns</li>
          <li>Predictive alerts before customers feel the problem</li>
          <li>Approval-gated self-healing runbooks with verification</li>
          <li>Evidence-bounded RCA drafts and a living knowledge base</li>
        </ul>
      </div>

      {/* login panel */}
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center',
        alignItems: 'center', background: 'var(--page)', padding: '2rem' }}>
        <form className="card" style={{ width: 380 }} onSubmit={submit}>
          <h2 style={{ marginTop: 0 }}>Sign in</h2>
          <div className="field"><label>Work email</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoFocus /></div>
          <div className="field"><label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" /></div>
          {error && <div className="evd metric" style={{ marginBottom: '.6rem' }}>⛔ {error}</div>}
          <button className="btn brand" style={{ width: '100%' }} disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        {personas.length > 0 && (
          <div className="card" style={{ width: 380 }}>
            <h2 style={{ marginTop: 0, fontSize: '.85rem' }}>Demo personas <span style={{ color: 'var(--muted)', fontWeight: 400 }}>(password: {hint})</span></h2>
            <div style={{ display: 'grid', gap: '.35rem' }}>
              {personas.map((p) => (
                <button key={p.email} type="button" className="btn" onClick={(e) => submit(e, p.email)}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', textAlign: 'left' }}>
                  <span><b>{p.name}</b> <span style={{ color: 'var(--muted)' }}>· {p.tenant}</span></span>
                  <span className={`badge ${roleColor[p.role] || 'neutral'}`}>{p.role}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
