import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, Kpi, PageHeader, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api, session } from '../services/api';
import type { Branch } from '../services/types';
import { CHANNEL_LABEL, dateTime, isoDay, num, pct, shortDate, zar, zarCompact } from '../utils/format';

export default function BranchDetail() {
  const { id } = useParams();
  const role = session.user()?.role ?? '';
  const canEdit = role === 'admin' || role === 'operations';
  const [start, setStart] = useState(isoDay(-29));
  const perf = useApi(() => api.get<any>(`/api/v1/branches/${id}/performance`, { start }), [id, start]);
  const health = useApi(() => api.get<any>(`/api/v1/branches/${id}/integration-health`), [id]);
  const [edit, setEdit] = useState<Partial<Branch> | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const action = useAction();

  if (perf.loading && !perf.data) return <Spinner />;
  if (perf.error) return <ErrorBox error={perf.error} onRetry={perf.reload} />;
  const b: Branch = perf.data.branch;
  const s = perf.data.summary;

  const save = async () => {
    const r = await action.run(() => api.patch<Branch>(`/api/v1/branches/${id}`, edit));
    if (r) { setEdit(null); setToast('Branch updated (audit logged)'); void perf.reload(); }
  };

  return (
    <>
      <PageHeader title={`${b.name}`} subtitle={<><Link to="/branches">Branches</Link> / <span className="mono">{b.code}</span> · {b.city}, {b.province}</>}
        actions={<>
          <select className="input" value={start} onChange={(e) => setStart(e.target.value)} aria-label="Period">
            <option value={isoDay(-6)}>Last 7 days</option><option value={isoDay(-29)}>Last 30 days</option><option value={isoDay(-59)}>Last 60 days</option>
          </select>
          {canEdit && !edit && <Button variant="secondary" onClick={() => setEdit({ pos_location_ref: b.pos_location_ref, digital_channels: b.digital_channels, is_active: b.is_active, phone: b.phone })}>Edit configuration</Button>}
        </>} />
      <div className="grid grid-kpi">
        <Kpi label="Orders" value={num(s.total_orders)} />
        <Kpi label="Sales" value={zar(s.total_sales_zar)} tone="good" />
        <Kpi label="Avg ticket" value={zar(s.average_order_value_zar)} />
        <Kpi label="Payment success" value={pct(s.payments.success_rate)} tone={s.payments.success_rate > 95 ? 'good' : 'warn'} hint={`${s.payments.failed} failed`} />
        <Kpi label="Integration failures" value={num(health.data?.recent_failures)} tone={health.data?.recent_failures ? 'warn' : 'good'} hint="last 50 calls" />
      </div>
      <div className="grid grid-3 mt">
        <Card title="Daily sales" className="span-2">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={perf.data.trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tickFormatter={shortDate} fontSize={11} />
              <YAxis tickFormatter={zarCompact} fontSize={11} width={52} />
              <Tooltip formatter={(v: number) => zar(v)} labelFormatter={shortDate} />
              <Bar dataKey="revenue" fill="#ea580c" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Configuration">
          <ErrorBox error={action.error} />
          {edit ? (
            <div className="stack">
              <Field label="Simphony location ref (POS assignment)"><input value={edit.pos_location_ref ?? ''} onChange={(e) => setEdit({ ...edit, pos_location_ref: e.target.value })} /></Field>
              <Field label="Phone"><input value={edit.phone ?? ''} onChange={(e) => setEdit({ ...edit, phone: e.target.value })} /></Field>
              <Field label="Digital channels">
                <div className="checks">{['uber_eats', 'mr_d', 'web'].map((c) => (
                  <label key={c}><input type="checkbox" checked={edit.digital_channels?.includes(c)} onChange={() => setEdit({ ...edit, digital_channels: edit.digital_channels?.includes(c) ? edit.digital_channels.filter((x) => x !== c) : [...(edit.digital_channels ?? []), c] })} /> {CHANNEL_LABEL[c]}</label>))}</div>
              </Field>
              <label className="checks"><input type="checkbox" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> Branch active</label>
              <div className="form-actions"><Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button><Button busy={action.busy} onClick={save}>Save</Button></div>
            </div>
          ) : (
            <>
              <div className="stat-row"><span>POS</span><span>Micros Simphony · <span className="mono">{b.pos_location_ref || '—'}</span></span></div>
              <div className="stat-row"><span>Payment provider</span><span>Transaction Junction</span></div>
              <div className="stat-row"><span>Channels</span><span className="chip-list">{b.digital_channels.map((c) => <Badge key={c} value={CHANNEL_LABEL[c]} tone="info" />)}</span></div>
              <div className="stat-row"><span>Status</span><Badge value={b.is_active ? 'healthy' : 'disabled'} /></div>
              <div className="stat-row"><span>Phone</span><span>{b.phone}</span></div>
              <div className="stat-row"><span>Opened</span><span>{b.opened_on ?? '—'}</span></div>
            </>
          )}
        </Card>
      </div>
      <div className="grid grid-2 mt">
        <Card title="Top products">
          <DataTable dense rows={perf.data.top_products} rowKey={(r: any) => r.sku} columns={[
            { key: 'name', header: 'Product' }, { key: 'quantity', header: 'Qty', align: 'right' },
            { key: 'revenue', header: 'Revenue', align: 'right', render: (r: any) => zar(r.revenue) }]} />
        </Card>
        <Card title="Integration health for this branch">
          {health.data?.orders_failed_to_reach_pos?.length > 0 && (
            <div className="alert alert-warn">{health.data.orders_failed_to_reach_pos.length} order(s) failed to reach the POS. <Link to="/pos">Retry in POS hub →</Link></div>)}
          <DataTable dense rows={health.data?.last_errors ?? []} rowKey={(r: any) => r.at + r.operation} empty="No recent integration errors"
            columns={[{ key: 'integration', header: 'Integration' }, { key: 'operation', header: 'Operation' },
              { key: 'error', header: 'Error', render: (r: any) => <span className="small">{r.error}</span> }, { key: 'at', header: 'When', render: (r: any) => dateTime(r.at) }]} />
        </Card>
      </div>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}
