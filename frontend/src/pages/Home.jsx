import { useEffect, useState } from 'react'
import { api, withTenant } from '../api'
import Chart from '../Chart'
import { PageHead, HealthDot } from '../bits'

const PREFERRED_METRIC = {
  'checkout-api': 'db_pool_utilization', 'payment-api': 'heap_used_pct',
  'fulfillment-worker': 'queue_depth', 'trading-api': 'latency_p99_ms',
  'risk-engine': 'error_rate_pct', 'notification-svc': 'queue_depth',
}

export default function Home() {
  const [ov, setOv] = useState(null)
  const [metrics, setMetrics] = useState(null)

  const load = async () => {
    setOv(await api(withTenant('/api/overview')))
    setMetrics(await api(withTenant('/api/metrics')))
  }
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t) }, [])

  if (!ov || !metrics) return <div className="page"><div className="card spin">Loading operational state…</div></div>
  const k = ov.kpis
  const picks = Object.keys(metrics.metrics).slice(0, 6)
    .map((svc) => [svc, PREFERRED_METRIC[svc] || 'latency_p99_ms'])
  return (
    <div className="page">
      <PageHead icon="🏠" tint="linear-gradient(135deg,#0176d3,#1b96ff)" crumb="Operations Cloud"
        title="Executive Overview"
        desc="Detect · Explain · Predict · Resolve · Learn — one intelligence layer over your observability stack." />

      <div className="grid g4">
        <StatCard label="Active incidents" value={k.active_incidents} color={k.active_incidents ? 'var(--crit)' : 'var(--good)'} hint="metric + log + change correlation" />
        <StatCard label="Predicted incidents" value={k.predicted_incidents} color={k.predicted_incidents ? 'var(--warn)' : 'var(--good)'} hint="forecast inside 60-min horizon" />
        <StatCard label="Anomalous log patterns" value={k.error_clusters} color="var(--s2)" hint="auto-templated clusters" />
        <StatCard label="Log lines in PostgreSQL" value={k.log_lines_analyzed.toLocaleString()} color="var(--s1)" hint={`${k.automations_run} automations audited`} />
      </div>

      <div className="card">
        <h2>Service health</h2>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>Service</th><th>Status</th><th>Owner</th><th>On-call</th><th>Criticality</th></tr></thead>
          <tbody>
            {ov.services.map((s) => (
              <tr key={s.name}>
                <td><HealthDot health={s.health} /><b>{s.name}</b></td>
                <td style={{ textTransform: 'capitalize' }}>{s.health}</td>
                <td>{s.owner}</td><td className="mono">{s.oncall}</td><td>{s.criticality}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      <h2 style={{ fontSize: '.95rem', margin: '0 0 .6rem' }}>Key telemetry (last 60 minutes)</h2>
      <div className="grid g2">
        {picks.map(([svc, m]) => (
          <Chart key={svc + m} service={svc} metric={m} series={metrics.metrics[svc][m]} threshold={metrics.thresholds[m]} />
        ))}
      </div>
    </div>
  )
}

const StatCard = ({ label, value, color, hint }) => (
  <div className="card stat">
    <span className="label">{label}</span>
    <span className="value" style={{ color }}>{value}</span>
    <span className="hint">{hint}</span>
  </div>
)
