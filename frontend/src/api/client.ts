export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? 'Error inesperado')
  }
  return res
}

export async function login(username: string, password: string): Promise<{ username: string }> {
  const res = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  return res.json()
}

export async function logout(): Promise<void> {
  await request('/api/auth/logout', { method: 'POST' })
}

export async function me(): Promise<{ username: string } | null> {
  try {
    return await (await request('/api/auth/me')).json()
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null
    throw e
  }
}
