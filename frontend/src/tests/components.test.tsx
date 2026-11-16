import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { DataTable } from '../components/DataTable';
import { Badge, ErrorBox } from '../components/ui';
import Dashboard from '../pages/Dashboard';
import LoginPage from '../pages/Login';
import { ApiError, session } from '../services/api';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('DataTable', () => {
  const rows = [{ id: 1, name: 'Sandton', revenue: 300 }, { id: 2, name: 'Umhlanga', revenue: 900 }, { id: 3, name: 'Ballito', revenue: 100 }];
  const cols = [{ key: 'name', header: 'Branch' }, { key: 'revenue', header: 'Revenue' }];

  it('renders rows and sorts when a header is clicked', async () => {
    render(<DataTable rows={rows} columns={cols} rowKey={(r) => r.id} />);
    const names = () => screen.getAllByRole('row').slice(1).map((r) => r.textContent);
    expect(names()[0]).toContain('Sandton');
    await userEvent.click(screen.getByRole('button', { name: 'Revenue' }));
    expect(names()[0]).toContain('Ballito');
    await userEvent.click(screen.getByRole('button', { name: /Revenue/ }));
    expect(names()[0]).toContain('Umhlanga');
  });

  it('calls onRowClick for drill-down and shows an empty state', async () => {
    const click = vi.fn();
    const { rerender } = render(<DataTable rows={rows} columns={cols} rowKey={(r) => r.id} onRowClick={click} />);
    await userEvent.click(screen.getByText('Umhlanga'));
    expect(click).toHaveBeenCalledWith(rows[1]);
    rerender(<DataTable rows={[]} columns={cols} rowKey={(r: any) => r.id} empty="No branches" />);
    expect(screen.getByText('No branches')).toBeInTheDocument();
  });

  it('paginates', async () => {
    const onPage = vi.fn();
    render(<DataTable rows={rows} columns={cols} rowKey={(r) => r.id} total={60} page={0} pageSize={25} onPage={onPage} />);
    expect(screen.getByText(/page 1 of 3/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(onPage).toHaveBeenCalledWith(1);
  });
});

describe('ui primitives', () => {
  it('maps statuses to badge tones', () => {
    render(<><Badge value="failed" /><Badge value="healthy" /><Badge value="SEV1" /></>);
    expect(screen.getByText('Failed')).toHaveClass('badge-bad');
    expect(screen.getByText('Healthy')).toHaveClass('badge-good');
    expect(screen.getByText('SEV1')).toHaveClass('badge-bad');
  });

  it('shows validation details and correlation id from API errors', () => {
    const err = new ApiError(422, 'Request validation failed', 'VALIDATION_ERROR',
      [{ loc: ['body', 'amount'], msg: 'must be > 0' }], 'corr-1');
    render(<ErrorBox error={err} />);
    expect(screen.getByRole('alert')).toHaveTextContent('amount: must be > 0');
    expect(screen.getByRole('alert')).toHaveTextContent('Reference: corr-1');
  });
});

describe('Login page', () => {
  it('validates input before calling the API', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    await userEvent.clear(screen.getByLabelText('Email'));
    await userEvent.type(screen.getByLabelText('Email'), 'not-an-email');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('Enter a valid email address')).toBeInTheDocument();
    expect(screen.getByText('Password must be at least 8 characters')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('logs in with the OAuth2 password flow and stores the session', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ access_token: 'jwt-abc', token_type: 'bearer', expires_in: 3600 }))
      .mockResolvedValueOnce(json({ email: 'finance@tableflow.local', full_name: 'Priya', role: 'finance', branch_id: null }));
    vi.stubGlobal('fetch', fetchMock);
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    await userEvent.click(screen.getByText(/finance@tableflow.local/));
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(session.token()).toBe('jwt-abc'));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/auth/login');
    expect(String(init.body)).toContain('username=finance%40tableflow.local');
    expect(session.user()?.role).toBe('finance');
    vi.unstubAllGlobals();
  });

  it('shows the API error on bad credentials', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ error: { code: 'HTTP_401', message: 'Incorrect email or password' } }, 401)));
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password');
    vi.unstubAllGlobals();
  });
});

describe('Executive dashboard', () => {
  it('renders KPIs from the dashboard API (frontend ↔ backend contract)', async () => {
    session.set('t', { email: 'a@b.co', full_name: 'A', role: 'admin', branch_id: null });
    const summary = {
      period: { start: '2026-10-18', end: '2026-11-16', branch_id: null }, branches: 12, total_orders: 5257,
      total_sales_zar: 1154119.6, average_order_value_zar: 219.54,
      payments: { successful: 4999, failed: 206, pending: 1, success_rate: 96.04 },
      integration_health: { healthy: 6, total: 7, items: [{ id: 1, name: 'Loyalty Platform', status: 'degraded', kind: 'loyalty', avg_response_ms: 130 }] },
      api_request_volume: { integration_calls: 10508, api_requests_since_start: 42 }, failed_webhook_events: 10,
      system: { uptime_seconds: 3600, latency_ms: { p50: 4, p95: 20, p99: 40 }, error_rate: 0 },
    };
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(json(
      url.includes('/summary') ? summary : url.includes('/branches') && !url.includes('performance') ? [] : []))));
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(await screen.findByRole('button', { name: 'Failed payments' })).toHaveTextContent('206');
    expect(screen.getByRole('button', { name: 'Integration health' })).toHaveTextContent('6/7');
    expect(screen.getByRole('button', { name: 'Total sales' })).toHaveTextContent('R1.2m');
    expect(screen.getByText('Loyalty Platform')).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
