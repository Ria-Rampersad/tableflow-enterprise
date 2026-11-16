import { useState } from 'react';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, JsonView, Kpi, Modal, PageHeader, SimulatedTag, Spinner } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Order, Paged } from '../services/types';
import { CHANNEL_LABEL, dateTime, zar } from '../utils/format';
import { OrderDetail } from './Orders';

export default function DigitalOrders() {
  const [channel, setChannel] = useState('uber_eats');
  const [branch, setBranch] = useState('DBN-UML');
  const [last, setLast] = useState<any>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const orders = useApi(() => api.get<Paged<Order>>('/api/v1/orders', { channel, limit: 30 }), [channel]);
  const failed = useApi(() => api.get<Paged<Order>>('/api/v1/orders', { channel, status: 'failed', limit: 1 }), [channel]);
  const cancelled = useApi(() => api.get<Paged<Order>>('/api/v1/orders', { channel, status: 'cancelled', limit: 1 }), [channel]);
  const branches = useApi(() => api.get<string[]>('/api/v1/simulate/branches-with-channel', { provider: channel }), [channel]);
  const action = useAction();

  const send = async (opts: { repeat?: boolean; corrupt?: boolean } = {}) => {
    const r = await action.run(() => api.post<any>('/api/v1/simulate/partner-order', {
      provider: channel, branch_code: branch, corrupt_total: !!opts.corrupt,
      repeat_external_ref: opts.repeat ? (channel === 'uber_eats' ? last?.provider_payload?.id : last?.provider_payload?.orderReference) : undefined,
    }));
    if (r) { setLast(r); setTimeout(() => { void orders.reload(); void failed.reload(); }, 300); }
  };
  const cancel = async (id: number) => {
    if (await action.run(() => api.post('/api/v1/simulate/provider-cancel', { order_id: id }))) { void orders.reload(); void cancelled.reload(); }
  };

  return (
    <>
      <PageHeader title="Digital Ordering Integrations" subtitle={<>Uber Eats and Mr D adapters: validation, mapping, POS forwarding, duplicate prevention <SimulatedTag /></>}
        actions={<div className="row gap-sm">{['uber_eats', 'mr_d'].map((c) => (
          <Button key={c} variant={c === channel ? 'primary' : 'secondary'} onClick={() => { setChannel(c); setLast(null); }}>{CHANNEL_LABEL[c]}</Button>))}</div>} />
      <div className="grid grid-kpi">
        <Kpi label={`${CHANNEL_LABEL[channel]} orders`} value={orders.data?.total ?? '…'} />
        <Kpi label="Failed (POS not reached)" value={failed.data?.total ?? '…'} tone={failed.data?.total ? 'bad' : 'good'} />
        <Kpi label="Cancelled by provider/customer" value={cancelled.data?.total ?? '…'} />
      </div>
      <div className="grid grid-3 mt">
        <Card title="Provider simulator" subtitle="Sends a provider-shaped payload through the real ingest pipeline">
          <ErrorBox error={action.error} />
          <Field label="Branch (channel enabled)">
            <select value={branch} onChange={(e) => setBranch(e.target.value)}>
              {(branches.data ?? []).map((b) => <option key={b}>{b}</option>)}
              {!branches.data?.includes(branch) && <option>{branch}</option>}
            </select>
          </Field>
          <div className="stack mt">
            <Button busy={action.busy} onClick={() => send()}>Send new {CHANNEL_LABEL[channel]} order</Button>
            <Button variant="secondary" busy={action.busy} disabled={!last} onClick={() => send({ repeat: true })}>Re-send same order (duplicate test)</Button>
            <Button variant="secondary" busy={action.busy} onClick={() => send({ corrupt: true })}>Send order with wrong total (validation test)</Button>
          </div>
          {last && (
            <div className="mt">
              <div className={`alert ${last.result.duplicate ? 'alert-warn' : 'alert-info'}`}>
                <div><strong>{last.result.message}</strong><br />{last.result.order_number} · status <Badge value={last.result.status} /></div>
              </div>
              <details open><summary className="small muted">Provider payload sent</summary><JsonView value={last.provider_payload} /></details>
            </div>)}
        </Card>
        <Card title={`Recent ${CHANNEL_LABEL[channel]} orders`} className="span-2" actions={<Button variant="ghost" onClick={orders.reload}>Refresh</Button>}>
          {orders.loading && !orders.data ? <Spinner /> : (
            <DataTable dense rows={orders.data?.items ?? []} rowKey={(o) => o.id} onRowClick={(o) => setSelected(o.id)} columns={[
              { key: 'order_number', header: 'Order', render: (o) => <span className="mono small">{o.order_number}</span> },
              { key: 'external_ref', header: 'Provider ref', render: (o) => <span className="mono small">{(o.external_ref ?? '').slice(0, 18)}</span> },
              { key: 'branch_name', header: 'Branch' },
              { key: 'created_at', header: 'Received', render: (o) => dateTime(o.created_at) },
              { key: 'status', header: 'Status', render: (o) => <Badge value={o.status} /> },
              { key: 'total', header: 'Total', align: 'right', render: (o) => zar(o.total) },
              { key: 'act', header: '', render: (o) => !['cancelled', 'completed'].includes(o.status) &&
                <Button variant="ghost" onClick={(e) => { e.stopPropagation(); void cancel(o.id); }}>Provider cancel</Button> },
            ]} />)}
        </Card>
      </div>
      <Modal title="Order detail" open={selected !== null} onClose={() => setSelected(null)} wide>
        {selected !== null && <OrderDetail orderId={selected} onChanged={orders.reload} />}
      </Modal>
    </>
  );
}
