import { store } from './store'

export async function api(path, { method = 'GET', body, headers = {}, raw = false } = {}) {
  const options = { method, credentials: 'include', headers: { ...headers } }
  if (body !== undefined) {
    options.body = typeof body === 'string' ? body : JSON.stringify(body)
    options.headers['Content-Type'] = 'application/json'
  }
  if (!['GET', 'HEAD'].includes(method) && store.csrf) {
    options.headers['X-CSRF-Token'] = store.csrf
  }
  const response = await fetch(`/api${path}`, options)
  if (raw) {
    if (!response.ok) throw await toError(response)
    return response
  }
  const text = await response.text()
  let payload = null
  try { payload = text ? JSON.parse(text) : null } catch { /* non-json */ }
  if (!response.ok) {
    if (response.status === 401) {
      store.user = null
      window.dispatchEvent(new CustomEvent('dlr:unauthorized'))
    }
    throw errorFrom(payload, response.status)
  }
  return payload?.data
}

async function toError(response) {
  let payload = null
  try { payload = await response.json() } catch { /* ignore */ }
  return errorFrom(payload, response.status)
}

function errorFrom(payload, status) {
  const error = new Error(payload?.error?.message || `请求失败 (${status})`)
  error.code = payload?.error?.code || 'REQUEST_FAILED'
  error.status = status
  error.details = payload?.error?.details
  return error
}

export function downloadText(filename, text, type = 'text/plain;charset=utf-8') {
  const blob = new Blob([text], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
