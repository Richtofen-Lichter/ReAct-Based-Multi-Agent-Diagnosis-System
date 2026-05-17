const API = '/api/v1'

export function useApi() {
  async function get(path) {
    const r = await fetch(`${API}${path}`)
    const data = await r.json()
    if (!r.ok) throw new Error(data?.message || data?.detail || `HTTP ${r.status}`)
    return data
  }

  async function post(path, body, opts = {}) {
    const r = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      body: JSON.stringify(body),
      signal: opts.signal,
    })
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.message || data?.detail || `HTTP ${r.status}`)
    return data
  }

  async function postForm(path, formData, opts = {}) {
    const r = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { ...opts.headers },
      body: formData,
    })
    const data = await r.json().catch(() => null)
    return { ok: r.ok, status: r.status, data }
  }

  async function del(path, opts = {}) {
    const r = await fetch(`${API}${path}`, {
      method: 'DELETE',
      headers: { ...opts.headers },
    })
    const data = await r.json().catch(() => null)
    return { ok: r.ok, status: r.status, data }
  }

  return { get, post, postForm, del, API }
}
