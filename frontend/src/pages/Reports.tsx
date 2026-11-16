import { useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { DataTable } from '../components/DataTable';
import { Button, Card, ErrorBox, PageHeader, Spinner } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import { isoDay, titleCase } from '../utils/format';

// x-axis key and series to chart per report
const CHART: Record<string, { x: string; y: string[]; kind: 'bar' | 'line' }> = {
  'daily-sales': { x: 'date', y: ['revenue'], kind: 'line' },
  'monthly-sales': { x: 'month', y: ['revenue'], kind: 'bar' },
  'branch-performance': { x: 'code', y: ['revenue'], kind: 'bar' },
  'payment-success': { x: 'branch', y: ['success_rate'], kind: 'bar' },
  'order-volumes': { x: 'channel', y: ['completed', 'cancelled', 'failed'], kind: 'bar' },
  'integration-performance': { x: 'integration', y: ['avg_ms', 'failed'], kind: 'bar' },
  'loyalty-activity': { x: 'date', y: ['points_earned', 'points_redeemed'], kind: 'line' },
  'top-products': { x: 'sku', y: ['revenue'], kind: 'bar' },
};
const COLORS = ['#ea580c', '#2563eb', '#dc2626', '#16a34a'];

export default function Reports() {
  const [name, setName] = useState('daily-sales');
  const [start, setStart] = useState(isoDay(-29));
  const [end, setEnd] = useState(isoDay(0));
  const list = useApi(() => api.get<string[]>('/api/v1/reports'), []);
  const report = useApi(() => api.get<{ rows: any[] }>(`/api/v1/reports/${name}`, { start, end }), [name, start, end]);
  const rows = useMemo(() => report.data?.rows ?? [], [report.data]);
  const cols = useMemo(() => (rows[0] ? Object.keys(rows[0]) : []).map((k) => ({
    key: k, header: titleCase(k), align: typeof rows[0][k] === 'number' ? 'right' as const : 'left' as const,
    render: (r: any) => typeof r[k] === 'number' ? r[k].toLocaleString('en-ZA', { maximumFractionDigits: 2 }) : String(r[k] ?? '—'),
  })), [rows]);
  const chart = CHART[name];

  return (
    <>
      <PageHeader title="Reporting & Analytics" subtitle="Operational reports from PostgreSQL · historical analytics are modelled in Snowflake (see /snowflake)"
        actions={<>
          <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} aria-label="Start" />
          <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} aria-label="End" />
          <Button variant="secondary" onClick={() => api.download(`/api/v1/reports/${name}`, { start, end, format: 'csv' }, `${name}.csv`)}>Download CSV</Button>
        </>} />
      <div className="chip-list" style={{ marginBottom: 16 }}>
        {(list.data ?? Object.keys(CHART)).map((r) => (
          <button key={r} className={`btn ${r === name ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setName(r)}>{titleCase(r.replace(/-/g, '_'))}</button>))}
      </div>
      <ErrorBox error={report.error} onRetry={report.reload} />
      {report.loading ? <Spinner /> : (
        <>
          {chart && rows.length > 0 && (
            <Card title={titleCase(name.replace(/-/g, '_'))}>
              <ResponsiveContainer width="100%" height={300}>
                {chart.kind === 'line' ? (
                  <LineChart data={rows}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey={chart.x} fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Legend />
                    {chart.y.map((y, i) => <Line key={y} dataKey={y} stroke={COLORS[i]} dot={false} strokeWidth={2} />)}</LineChart>
                ) : (
                  <BarChart data={rows}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey={chart.x} fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Legend />
                    {chart.y.map((y, i) => <Bar key={y} dataKey={y} fill={COLORS[i]} radius={[4, 4, 0, 0]} />)}</BarChart>
                )}
              </ResponsiveContainer>
            </Card>)}
          <Card className="mt" title={`${rows.length} rows`}>
            <DataTable dense rows={rows} rowKey={(r) => JSON.stringify(r)} columns={cols} empty="No data for this period" />
          </Card>
        </>)}
    </>
  );
}
