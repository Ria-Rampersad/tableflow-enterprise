import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { DataTable } from '../components/DataTable';
import { Badge, Card, ErrorBox, Kpi, PageHeader, Spinner } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Branch, BranchPerf, DashboardSummary } from '../services/types';
import { duration, isoDay, num, pct, shortDate, zar, zarCompact } from '../utils/format';

const CHANNEL_COLORS: Record<string, string> = { in_store: '#ea580c', uber_eats: '#16a34a', mr_d: '#dc2626', web: '#2563eb' };

export default function Dashboard() {
  const navigate = useNavigate();
  const [start, setStart] = useState(isoDay(-29));
  const [end, setEnd] = useState(isoDay(0));
  const [branchId, setBranchId] = useState('');
  const q = { start, end, branch_id: branchId || undefined };

  const branches = useApi(() => api.get<Branch[]>('/api/v1/branches'), []);
  const summary = useApi(() => api.get<DashboardSummary>('/api/v1/dashboard/summary', q), [start, end, branchId]);
  const trend = useApi(() => api.get<any[]>('/api/v1/dashboard/revenue-trend', q), [start, end, branchId]);
  const tx = useApi(() => api.get<any[]>('/api/v1/dashboard/daily-transactions', q), [start, end, branchId]);
  const perf = useApi(() => api.get<BranchPerf[]>('/api/v1/dashboard/branch-performance', { start, end }), [start, end]);

  const s = summary.data;
  const preset = (days: number) => { setStart(isoDay(-(days - 1))); setEnd(isoDay(0)); };

  return (
    <>
      <PageHeader title="Executive Dashboard"
        subtitle={s ? `${shortDate(s.period.start)} – ${shortDate(s.period.end)} · all amounts in ZAR incl. VAT` : 'Loading…'}
        actions={<>
          <div className="row gap-sm">
            {[1, 7, 30, 60].map((d) => <button key={d} className="btn btn-secondary" onClick={() => preset(d)}>{d === 1 ? 'Today' : `${d}d`}</button>)}
          </div>
          <input className="input" type="date" aria-label="Start date" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
          <input className="input" type="date" aria-label="End date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} />
          <select className="input" aria-label="Branch filter" value={branchId} onChange={(e) => setBranchId(e.target.value)}>
            <option value="">All branches</option>
            {branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </>} />

      <ErrorBox error={summary.error} onRetry={summary.reload} />
      {summary.loading && !s ? <Spinner /> : s && (
        <div className="grid grid-kpi">
          <Kpi label="Branches" value={num(s.branches)} hint="active restaurants" onClick={() => navigate('/branches')} />
          <Kpi label="Total orders" value={num(s.total_orders)} hint={`avg ticket ${zar(s.average_order_value_zar)}`} onClick={() => navigate('/orders')} />
          <Kpi label="Total sales" value={zarCompact(s.total_sales_zar)} hint={zar(s.total_sales_zar)} tone="good" />
          <Kpi label="Successful payments" value={num(s.payments.successful)} hint={`${pct(s.payments.success_rate)} success rate`} tone="good" onClick={() => navigate('/payments?status=captured')} />
          <Kpi label="Failed payments" value={num(s.payments.failed)} tone={s.payments.failed ? 'bad' : 'good'} hint="declines & gateway errors" onClick={() => navigate('/payments?status=failed')} />
          <Kpi label="Pending transactions" value={num(s.payments.pending)} tone={s.payments.pending ? 'warn' : 'default'} hint="initiated / authorised" onClick={() => navigate('/payments?status=authorised')} />
          <Kpi label="Integration health" value={`${s.integration_health.healthy}/${s.integration_health.total}`} tone={s.integration_health.healthy === s.integration_health.total ? 'good' : 'warn'} hint="healthy integrations" onClick={() => navigate('/integrations')} />
          <Kpi label="API request volume" value={num(s.api_request_volume.integration_calls)} hint={`${num(s.api_request_volume.api_requests_since_start)} API calls since start`} />
          <Kpi label="Failed webhooks" value={num(s.failed_webhook_events)} tone={s.failed_webhook_events ? 'bad' : 'good'} hint="failed or rejected" onClick={() => navigate('/webhooks?status=failed')} />
          <Kpi label="System uptime" value={duration(s.system.uptime_seconds)} hint={`p95 ${s.system.latency_ms.p95} ms · ${pct(s.system.error_rate * 100, 2)} 5xx`} />
        </div>
      )}

      <div className="grid grid-3 mt">
        <Card title="Revenue trend by channel" subtitle="Daily sales, stacked by ordering channel" className="span-2">
          {trend.loading ? <Spinner /> : (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={trend.data ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tickFormatter={shortDate} fontSize={11} />
                <YAxis tickFormatter={zarCompact} fontSize={11} width={56} />
                <Tooltip formatter={(v: number) => zar(v)} labelFormatter={shortDate} />
                <Legend />
                {Object.entries(CHANNEL_COLORS).map(([k, c]) => (
                  <Area key={k} type="monotone" dataKey={k} name={k.replace('_', ' ')} stackId="1" stroke={c} fill={c} fillOpacity={0.25} />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Integration health" actions={<button className="btn btn-ghost" onClick={() => navigate('/integrations')}>Open →</button>}>
          {s?.integration_health.items.map((i) => (
            <div key={i.id} className="stat-row">
              <span><span className={`dot dot-${i.status}`} />{i.name}</span>
              <span className="muted">{i.avg_response_ms} ms <Badge value={i.status} /></span>
            </div>
          ))}
        </Card>
      </div>

      <div className="grid grid-3 mt">
        <Card title="Daily transaction summary" subtitle="Payment outcomes per day">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={tx.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tickFormatter={shortDate} fontSize={11} />
              <YAxis fontSize={11} width={36} />
              <Tooltip labelFormatter={shortDate} />
              <Legend />
              <Bar dataKey="successful" stackId="a" fill="#16a34a" />
              <Bar dataKey="failed" stackId="a" fill="#dc2626" />
              <Bar dataKey="pending" stackId="a" fill="#eab308" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Branch performance" subtitle="Click a branch to drill down" className="span-2">
          <ErrorBox error={perf.error} />
          <DataTable dense rows={perf.data ?? []} rowKey={(r) => r.branch_id} onRowClick={(r) => navigate(`/branches/${r.branch_id}`)}
            columns={[
              { key: 'name', header: 'Branch', render: (r) => <><strong>{r.name}</strong><div className="muted small">{r.city}, {r.province}</div></> },
              { key: 'orders', header: 'Orders', align: 'right', render: (r) => num(r.orders) },
              { key: 'revenue', header: 'Revenue', align: 'right', render: (r) => zar(r.revenue) },
              { key: 'avg_ticket', header: 'Avg ticket', align: 'right', render: (r) => zar(r.avg_ticket) },
              { key: 'failed_payments', header: 'Failed pay.', align: 'right' },
              { key: 'failed_orders', header: 'POS fails', align: 'right' },
            ]} />
        </Card>
      </div>
    </>
  );
}
