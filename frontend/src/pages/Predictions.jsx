import { useEffect, useState } from 'react'
import { api, withTenant } from '../api'
import { PageHead } from '../bits'

export default function Predictions() {
  const [d, setD] = useState(null)
  useEffect(() => { api(withTenant('/api/predictions')).then(setD) }, [])
  if (!d) return <div className="page"><div className="card spin">Fitting trend models…</div></div>

  return (
    <div className="page">
      <PageHead icon="🔮" tint="linear-gradient(135deg,#4a3aa7,#9085e9)" crumb="Operations Cloud"
        title="Predictive Alerts"
        desc="Explainable trend models forecast pool exhaustion, JVM pressure, latency and queue backlogs — with time-to-breach and confidence, before customers feel it." />

      <div className="card">
        <h2>Active breaches (now)</h2>
        {d.breaches.length === 0 && <div className="evd good">No live threshold breaches.</div>}
        <div className="grid g3">
          {d.breaches.map((b, i) => (
            <div className="card" key={i} style={{ marginBottom: 0 }}>
              <span className={`badge ${b.level === 'critical' ? 'sev1' : 'sev3'}`}>{b.level}</span>
              <div style={{ fontWeight: 700, margin: '.4rem 0 .1rem' }}>{b.title}</div>
              <div style={{ color: 'var(--muted)', fontSize: '.74rem' }}>{b.service}</div>
              <div className="stat" style={{ marginTop: '.3rem' }}>
                <span className="value" style={{ color: b.level === 'critical' ? 'var(--crit)' : 'var(--warn)', fontSize: '1.5rem' }}>
                  {b.value.toLocaleString()}
                </span>
                <span className="hint">threshold {b.threshold}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>Forecasts (next 60 minutes)</h2>
        {d.predictions.length === 0 && <div className="evd good">No forecasted breaches inside the horizon.</div>}
        <div className="grid g3">
          {d.predictions.map((p, i) => (
            <div className="card" key={i} style={{ marginBottom: 0 }}>
              <span className="badge brand">forecast</span>
              <div style={{ fontWeight: 700, margin: '.4rem 0 .1rem' }}>{p.title}</div>
              <div style={{ color: 'var(--muted)', fontSize: '.74rem' }}>{p.service} · <span className="mono">{p.metric}</span></div>
              <div className="stat" style={{ marginTop: '.3rem' }}>
                <span className="value" style={{ color: 'var(--warn)', fontSize: '1.5rem' }}>~{p.eta_minutes} min</span>
                <span className="hint">to critical ({p.threshold}{p.unit}) — now {p.current}{p.unit}</span>
                <span className="hint">confidence {(p.confidence * 100).toFixed(0)}% · slope {p.slope_per_min}/min</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
