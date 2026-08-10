import { useRef, useState } from 'react'

const FRIENDLY = {
  db_pool_utilization: ['DB pool utilization', '%'],
  heap_used_pct: ['JVM heap used', '%'],
  latency_p99_ms: ['Latency p99', 'ms'],
  queue_depth: ['Queue depth', 'msgs'],
  error_rate_pct: ['Error rate', '%'],
}

export default function Chart({ service, metric, series, threshold }) {
  const [name, unit] = FRIENDLY[metric] || [metric, '']
  const vals = series.map((p) => p[1])
  const cur = vals[vals.length - 1]
  const crit = threshold && cur >= threshold.critical
  const warn = threshold && cur >= threshold.warn
  const color = crit ? 'var(--crit)' : warn ? 'var(--warn)' : 'var(--s1)'
  const [tip, setTip] = useState(null)
  const svgRef = useRef(null)

  const W = 460, H = 110, P = 6
  let mn = Math.min(...vals), mx = Math.max(...vals)
  if (threshold) { mn = Math.min(mn, threshold.critical); mx = Math.max(mx, threshold.critical) }
  const span = mx - mn || 1
  mn -= span * 0.08; mx += span * 0.08
  const X = (i) => P + (i * (W - 2 * P)) / (vals.length - 1)
  const Y = (v) => H - P - ((v - mn) * (H - 2 * P)) / (mx - mn)
  const pts = vals.map((v, i) => `${X(i)},${Y(v)}`).join(' ')

  const onMove = (e) => {
    const r = svgRef.current.getBoundingClientRect()
    const i = Math.max(0, Math.min(vals.length - 1, Math.round(((e.clientX - r.left) / r.width) * (vals.length - 1))))
    setTip({ i, px: (X(i) / W) * r.width })
  }

  return (
    <div className="card chartbox">
      <div className="ctitle">{service} — {name}</div>
      <div className="cvalue" style={{ color }}>
        {cur.toLocaleString()} <span className="cunit">{unit}</span>
      </div>
      <svg ref={svgRef} width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
        onMouseMove={onMove} onMouseLeave={() => setTip(null)}>
        {[1, 2, 3].map((k) => (
          <line key={k} x1={P} x2={W - P} y1={P + (k * (H - 2 * P)) / 4} y2={P + (k * (H - 2 * P)) / 4}
            stroke="var(--grid)" strokeWidth="1" />
        ))}
        <polygon points={`${P},${H - P} ${pts} ${W - P},${H - P}`} fill={color} opacity="0.10" />
        {threshold && (
          <line x1={P} x2={W - P} y1={Y(threshold.critical)} y2={Y(threshold.critical)}
            stroke="var(--crit)" strokeWidth="1.5" strokeDasharray="5 4" opacity="0.6" />
        )}
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
        <circle cx={X(vals.length - 1)} cy={Y(cur)} r="3.5" fill={color} stroke="#fff" strokeWidth="2" />
        {tip && <line x1={X(tip.i)} x2={X(tip.i)} y1={P} y2={H - P} stroke="#9ab" strokeWidth="1" opacity="0.6" />}
      </svg>
      {tip && (
        <div className="tooltip" style={{ left: Math.min(tip.px + 10, 320), top: 40 }}>
          {vals.length - 1 - tip.i} min ago · {vals[tip.i].toLocaleString()} {unit}
        </div>
      )}
    </div>
  )
}
