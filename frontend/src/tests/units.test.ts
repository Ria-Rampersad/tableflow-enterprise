import { describe, expect, it, vi } from 'vitest';
import { validateBranch } from '../pages/Branches';
import { api, ApiError, session } from '../services/api';
import { duration, num, pct, titleCase, zar, zarCompact } from '../utils/format';

describe('format utils (ZAR / en-ZA)', () => {
  it('formats Rand', () => {
    expect(zar(1234.5).replace(/\s/g, ' ')).toMatch(/R\s?1[\s ]234,50/);
    expect(zar(null)).toBe('—');
  });
  it('compacts large Rand amounts for chart axes', () => {
    expect(zarCompact(1_250_000)).toBe('R1.3m');
    expect(zarCompact(12_400)).toBe('R12k');
    expect(zarCompact(950)).toBe('R950');
  });
  it('formats numbers, percentages, durations and labels', () => {
    expect(num(10614).replace(/\s/g, ' ')).toMatch(/10[\s ]614/);
    expect(pct(96.0417)).toBe('96.0%');
    expect(duration(3 * 86400 + 4 * 3600)).toBe('3d 4h');
    expect(duration(125)).toBe('2m 5s');
    expect(titleCase('missing_pos_record')).toBe('Missing Pos Record');
  });
});

describe('branch form validation', () => {
  const ok = { code: 'DBN-GTW', name: 'Gateway', city: 'Umhlanga', province: 'KwaZulu-Natal', address: '', phone: '0315550000',
    pos_location_ref: '', digital_channels: [] };
  it('accepts a valid branch', () => expect(validateBranch(ok)).toEqual({}));
  it('rejects bad code, missing name and bad phone', () => {
    const e = validateBranch({ ...ok, code: 'durban', name: '', phone: '12345' });
    expect(Object.keys(e).sort()).toEqual(['code', 'name', 'phone']);
  });
});

describe('api client', () => {
  it('adds bearer token + request id and unwraps the error envelope', async () => {
    session.set('tok123', { email: 'a@b.co', full_name: 'A', role: 'admin', branch_id: null });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: {
      code: 'AMOUNT_MISMATCH', message: 'Amount 1.00 does not match', correlation_id: 'abc' } }),
      { status: 422, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const err = (await api.post('/api/v1/payments', { a: 1 }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('AMOUNT_MISMATCH');
    expect(err.correlationId).toBe('abc');
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe('Bearer tok123');
    expect(init.headers['X-Request-ID']).toHaveLength(16);
    vi.unstubAllGlobals();
  });

  it('clears the session and emits logout on 401', async () => {
    session.set('expired', { email: 'a@b.co', full_name: 'A', role: 'admin', branch_id: null });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: 'Token expired' } }),
      { status: 401, headers: { 'content-type': 'application/json' } })));
    const listener = vi.fn();
    window.addEventListener('tableflow:logout', listener);
    await api.get('/api/v1/branches').catch(() => undefined);
    expect(session.token()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it('builds query strings and skips empty values', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    await api.get('/api/v1/orders', { status: 'failed', channel: '', branch_id: undefined, limit: 25 });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/orders?status=failed&limit=25');
    vi.unstubAllGlobals();
  });
});
