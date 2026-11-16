/**
 * Typed API client for the TableFlow FastAPI backend.
 *
 * - Adds the JWT bearer token to every request.
 * - Sends an X-Request-ID so a UI error can be traced in backend logs.
 * - Normalises the backend's error envelope ({ error: { code, message, details, correlation_id } })
 *   into an ApiError the UI can display.
 * - On 401 it clears the session so the user is sent back to the login page.
 *
 * Token storage: sessionStorage (cleared when the tab closes). For a production deployment an
 * httpOnly secure cookie set by the backend is safer against XSS - see the Security section of
 * documentation/02_TECHNICAL_STACK_EXPLANATION.md.
 */

const TOKEN_KEY = 'tableflow.token';
const USER_KEY = 'tableflow.user';

export interface SessionUser { email: string; full_name: string; role: string; branch_id: number | null; }

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public details?: unknown,
              public correlationId?: string) {
    super(message);
  }
}

export const session = {
  token: () => sessionStorage.getItem(TOKEN_KEY),
  user: (): SessionUser | null => {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  },
  set(token: string, user: SessionUser) {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  },
};

type Query = Record<string, string | number | boolean | null | undefined>;

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
  });
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(method: string, path: string, opts: { query?: Query; body?: unknown;
  form?: Record<string, string>; file?: File; headers?: Record<string, string> } = {}): Promise<T> {
  const headers: Record<string, string> = { 'X-Request-ID': crypto.randomUUID().slice(0, 16), ...opts.headers };
  const token = session.token();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) {
    body = new URLSearchParams(opts.form);
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
  } else if (opts.file) {
    const fd = new FormData();
    fd.append('file', opts.file);
    body = fd;
  } else if (opts.body !== undefined) {
    body = JSON.stringify(opts.body);
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(buildUrl(path, opts.query), { method, headers, body });
  const type = res.headers.get('content-type') ?? '';
  const payload = type.includes('application/json') ? await res.json() : await res.text();
  if (!res.ok) {
    if (res.status === 401 && path !== '/api/v1/auth/login') {
      session.clear();
      window.dispatchEvent(new Event('tableflow:logout'));
    }
    const err = (payload as any)?.error;
    const msg = typeof err?.message === 'string' ? err.message : JSON.stringify(err?.message ?? payload);
    throw new ApiError(res.status, msg, err?.code, err?.details, err?.correlation_id);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown, query?: Query, headers?: Record<string, string>) =>
    request<T>('POST', path, { body, query, headers }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  form: <T>(path: string, form: Record<string, string>) => request<T>('POST', path, { form }),
  upload: <T>(path: string, file: File) => request<T>('POST', path, { file }),
  download: async (path: string, query?: Query, filename = 'export.csv') => {
    const text = await request<string>('GET', path, { query });
    const blob = new Blob([text], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },
};

export async function login(email: string, password: string): Promise<SessionUser> {
  const tok = await api.form<{ access_token: string }>('/api/v1/auth/login', { username: email, password });
  sessionStorage.setItem(TOKEN_KEY, tok.access_token);
  const me = await api.get<SessionUser>('/api/v1/auth/me');
  session.set(tok.access_token, me);
  return me;
}
