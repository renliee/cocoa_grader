let csrfToken = '';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export function setCsrf(token) {
  csrfToken = token || '';
}

export function uploadKey() {
  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index++) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function api(path, { method = 'GET', body, headers: extraHeaders = {} } = {}) {
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const headers = { Accept: 'application/json', ...extraHeaders };
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken;
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method, headers, credentials: 'same-origin',
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Unable to connect to the server. Check your connection and retry.', 0);
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    let message = data?.detail;
    if (Array.isArray(message)) message = message.map(item => item.msg).join('; ');
    if (typeof message !== 'string') message = response.status === 503
      ? 'The analysis server is unavailable.' : `Request failed (status ${response.status}).`;
    throw new ApiError(message, response.status);
  }
  return data;
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

export const formatNumber = value => new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 }).format(Number(value));
export const shortDate = value => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(new Date(value));
