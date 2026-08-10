import { useEffect, useState } from 'react'
import { api, post } from '../api'
import { PageHead, Md, ModeTag } from '../bits'

export default function Logs() {
  const [clusters, setClusters] = useState([])
  const [summary, setSummary] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = async () => setClusters((await api('/api/logs/clusters')).clusters)
  useEffect(() => { load() }, [])

  const analyze = async () => {
    setBusy(true); setSummary(null)
    setSummary(await post('/api/logs/analyze'))
    setBusy(false)
  }

  return (
    <div className="page">
      <PageHead icon="📜" tint="linear-gradient(135deg,#eb6834,#f5a623)" crumb="Operations Cloud"
        title="AI Log Intelligence"
        desc="Every raw line is masked into a stable pattern and clustered. Anomalies surface instantly; AI explains them in seconds."
        actions={<button className="btn brand" onClick={analyze} disabled={busy}>⚡ AI: Summarize error situation</button>} />

      {busy && <div className="card spin">Reading clusters and generating the summary…</div>}
      {summary && (
        <div className="card">
          <h2>AI error summary</h2>
          <Md text={summary.summary} /><ModeTag mode={summary.mode} />
        </div>
      )}

      <div className="card">
        <h2>Error pattern clusters</h2>
        <div className="cardsub">Auto-templated: IDs, numbers and IPs are masked so thousands of lines collapse into a handful of patterns. Add new sources under Administration → Data Sources.</div>
        <div className="tablewrap"><table className="slds">
          <thead><tr><th>Service</th><th>Level</th><th>Pattern</th><th>Count</th><th>Status</th></tr></thead>
          <tbody>
            {clusters.map((c, i) => (
              <tr key={i}>
                <td>{c.service}</td><td>{c.level}</td>
                <td className="mono">{c.template.slice(0, 130)}</td>
                <td><b>{c.count}</b></td>
                <td>{c.matched_pattern ? <span className="badge sev1" title={c.pattern_severity}>⚑ {c.matched_pattern}</span> : c.anomalous ? <span className="badge sev2">anomalous</span> : <span className="badge neutral">baseline</span>}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>
    </div>
  )
}
