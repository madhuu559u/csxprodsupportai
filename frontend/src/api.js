export const currentUserEmail = () => localStorage.getItem('nexus_user') || ''
export const setCurrentUser = (email) => localStorage.setItem('nexus_user', email)
export const currentTenant = () => localStorage.getItem('nexus_tenant') || ''
export const setCurrentTenant = (slug) => localStorage.setItem('nexus_tenant', slug)

const authHeaders = () => {
  const u = currentUserEmail()
  return u ? { 'X-User-Email': u } : {}
}
export const withTenant = (path) => {
  const t = currentTenant()
  if (!t) return path
  return path + (path.includes('?') ? '&' : '?') + 'tenant=' + t
}

export const api = async (path, opts = {}) => {
  const r = await fetch(path, { ...opts, headers: { ...(opts.headers || {}), ...authHeaders() } })
  return r.json()
}
export const post = async (path, body) => {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body || {}),
  })
  const data = await r.json()
  if (!r.ok && data.detail && !data.error) data.error = data.detail
  return data
}
export const del = (path) => api(path, { method: 'DELETE' })

export const fmtAgo = (ts) => {
  const m = Math.round(Date.now() / 1000 / 60 - ts / 60)
  return m < 1 ? 'just now' : m < 60 ? `${m}m ago` : `${Math.round(m / 60)}h ago`
}

// AI provider display names
export const PROVIDER_LABEL = { openai: 'OpenAI', anthropic: 'Anthropic Claude', azure: 'Azure OpenAI', offline: 'Offline engine' }

// tiny markdown renderer (headings, bold, code, lists)
const escHtml = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
export function mdToHtml(t) {
  let h = escHtml(t || '')
  h = h.replace(/^### (.*)$/gm, '<h3>$1</h3>').replace(/^## (.*)$/gm, '<h2>$1</h2>').replace(/^# (.*)$/gm, '<h1>$1</h1>')
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>')
  h = h.replace(/^\s*[-*] (.*)$/gm, '<li>$1</li>').replace(/(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g, '<ul>$1</ul>')
  return h.split(/\n{2,}/).map((p) => (/^<(h\d|ul)/.test(p.trim()) ? p : '<p>' + p.replace(/\n/g, '<br/>') + '</p>')).join('')
}
