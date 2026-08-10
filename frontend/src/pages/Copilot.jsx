import { useEffect, useRef, useState } from 'react'
import { api, post } from '../api'
import { PageHead, Md, ModeTag } from '../bits'

const CHIPS = [
  'What is the current top incident and who owns it?',
  'What changed before this incident started?',
  'Which runbook should I run to fix it?',
  'Has something like this happened before?',
]

export default function Copilot() {
  const [msgs, setMsgs] = useState([
    { role: 'ai', text: "Hi — I'm your support copilot. I can see the live incident state, recent changes, service ownership and the runbook catalog. What do you need?" },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const logRef = useRef(null)

  useEffect(() => {
    api('/api/copilot/history').then((h) => {
      if (h.history?.length) {
        const prev = h.history.flatMap((x) => [
          { role: 'user', text: x.question }, { role: 'ai', text: x.answer, mode: x.provider }])
        setMsgs((m) => [...m, ...prev.slice(-10)])
      }
    })
  }, [])
  useEffect(() => { logRef.current?.scrollTo(0, 1e9) }, [msgs, busy])

  const send = async (q) => {
    const question = (q ?? input).trim()
    if (!question || busy) return
    setInput(''); setBusy(true)
    setMsgs((m) => [...m, { role: 'user', text: question }])
    const r = await post('/api/copilot', { question })
    setMsgs((m) => [...m, { role: 'ai', text: r.answer, mode: r.mode }])
    setBusy(false)
  }

  return (
    <div className="page">
      <PageHead icon="💬" tint="linear-gradient(135deg,#032d60,#0176d3)" crumb="Operations Cloud"
        title="L1 Support Copilot"
        desc="Grounded in live operational context — incidents, changes, ownership, runbooks and prior resolutions. Conversation history persists in PostgreSQL." />

      <div className="card chat">
        <div className="chatlog" ref={logRef}>
          {msgs.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === 'ai' ? <><Md text={m.text} />{m.mode && <ModeTag mode={m.mode} />}</> : m.text}
            </div>
          ))}
          {busy && <div className="msg ai spin">thinking…</div>}
        </div>
        <div className="chips">
          {CHIPS.map((c) => <button key={c} className="chip" onClick={() => send(c)}>{c}</button>)}
        </div>
        <div style={{ display: 'flex', gap: '.5rem' }}>
          <input style={{ flex: 1, border: '1px solid var(--border-strong)', borderRadius: '.35rem', padding: '.5rem .7rem', font: 'inherit' }}
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Ask about incidents, changes, ownership, runbooks…" />
          <button className="btn brand" onClick={() => send()} disabled={busy}>Send</button>
        </div>
      </div>
    </div>
  )
}
