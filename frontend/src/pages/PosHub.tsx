import { useState } from 'react';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, JsonView, Kpi, PageHeader, SimulatedTag, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Integration, IntegrationLog, Paged } from '../services/types';
import { CHANNEL_LABEL, dateTime, isoDay, num, zar } from '../utils/format';

export default function PosHub() {
  const status = useApi(() => api.get<any>('/api/v1/pos/status'), []);
  const integ: Integration | undefined = status.data?.integration;
  const logs = useApi(() => integ ? api.get<Paged<IntegrationLog>>(`/api/v1/integrations/${integ.id}/logs`, { limit: 15 })
    : Promise.resolve({ total: 0, items: [] }), [integ?.id]);
  const action = useAction();
  const [result, setResult] = useState<any>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [day, setDay] = useState(isoDay(-1));

  const run = async (label: string, fn: () => Promise<any>) => {
    const r = await action.run(fn);
    if (r) { setResult({ label, ...r }); setToast(`${label}: ${r.ok === false ? 'failed' : 'done'}`); void status.reload(); void logs.reload(); }
  };

  return (
    <>
      <PageHeader title="POS Integration Hub" subtitle={<>Oracle MICROS Simphony adapter: check creation, status updates, menu & transaction sync <SimulatedTag /></>}
        actions={<Button variant="secondary" onClick={() => { void status.reload(); void logs.reload(); }}>Refresh</Button>} />
      <ErrorBox error={status.error || action.error} />
      {status.loading && !status.data ? <Spinner /> : integ && (
        <div className="grid grid-kpi">
          <Kpi label="Connectivity" value={<Badge value={integ.status} />} hint={integ.config.simulate_outage ? 'Outage simulation ON' : `mode: ${integ.mode}`} tone={integ.status === 'healthy' ? 'good' : 'bad'} />
          <Kpi label="Avg response" value={`${integ.avg_response_ms} ms`} />
          <Kpi label="Requests" value={num(integ.total_requests)} hint={`${num(integ.total_failures)} failed`} />
          <Kpi label="Orders awaiting POS" value={status.data.failed_orders.length} tone={status.data.failed_orders.length ? 'bad' : 'good'} />
          <Kpi label="Last success" value={dateTime(integ.last_success_at)} />
        </div>)}
      <div className="grid grid-2 mt">
        <Card title="Failed POS requests" subtitle="Orders that could not be created as Simphony checks">
          <DataTable dense rows={status.data?.failed_orders ?? []} rowKey={(o: any) => o.id} empty="No failed POS orders 🎉" columns={[
            { key: 'order_number', header: 'Order', render: (o: any) => <span className="mono small">{o.order_number}</span> },
            { key: 'channel', header: 'Channel', render: (o: any) => CHANNEL_LABEL[o.channel] },
            { key: 'total', header: 'Total', align: 'right', render: (o: any) => zar(o.total) },
            { key: 'created_at', header: 'When', render: (o: any) => dateTime(o.created_at) },
            { key: 'act', header: '', render: (o: any) => <Button variant="secondary" busy={action.busy}
                onClick={() => run(`Retry ${o.order_number}`, () => api.post(`/api/v1/orders/${o.id}/forward-to-pos`).then((r: any) => ({ ok: r.forwarded, ...r })))}>Retry</Button> },
          ]} />
        </Card>
        <Card title="Branch POS operations" actions={<input className="input" type="date" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Business date" />}>
          <DataTable dense rows={status.data?.branches ?? []} rowKey={(b: any) => b.id} columns={[
            { key: 'code', header: 'Branch', render: (b: any) => <><span className="mono">{b.code}</span> <span className="muted small">{b.name}</span></> },
            { key: 'location_ref', header: 'locRef', render: (b: any) => <span className="mono small">{b.location_ref}</span> },
            { key: 'act', header: '', render: (b: any) => (
              <div className="row gap-sm">
                <Button variant="secondary" busy={action.busy} onClick={() => run(`Menu sync ${b.code}`, () => api.post(`/api/v1/pos/branches/${b.id}/menu-sync`))}>Menu sync</Button>
                <Button variant="secondary" busy={action.busy} onClick={() => run(`Transaction sync ${b.code}`, () => api.post(`/api/v1/pos/branches/${b.id}/transaction-sync`, undefined, { business_date: day }))}>Txn sync</Button>
              </div>) },
          ]} />
        </Card>
      </div>
      {result && <Card title={`Result: ${result.label}`} className="mt"><JsonView value={{ ...result, menu: result.menu ? `${result.menu.length} menu items (truncated)` : undefined }} /></Card>}
      <Card title="Simphony integration log" className="mt">
        <DataTable dense rows={logs.data?.items ?? []} rowKey={(l) => l.id} columns={[
          { key: 'created_at', header: 'Time', render: (l) => dateTime(l.created_at) },
          { key: 'operation', header: 'Operation' },
          { key: 'status', header: 'Status', render: (l) => <Badge value={l.status} /> },
          { key: 'attempt', header: 'Attempt', align: 'right' },
          { key: 'http_status', header: 'HTTP', align: 'right' },
          { key: 'response_ms', header: 'ms', align: 'right' },
          { key: 'error_message', header: 'Error', render: (l) => <span className="small">{l.error_message ?? ''}</span> },
        ]} />
      </Card>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}
