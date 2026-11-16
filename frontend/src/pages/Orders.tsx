import { useState } from 'react';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, JsonView, Modal, PageHeader, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Branch, Order, Paged } from '../services/types';
import { CHANNEL_LABEL, dateTime, zar } from '../utils/format';

const NEXT: Record<string, string[]> = {
  received: ['accepted', 'cancelled'], failed: ['cancelled'], accepted: ['preparing', 'ready', 'cancelled'],
  preparing: ['ready', 'cancelled'], ready: ['completed'],
};
const PAGE = 25;

export function OrderDetail({ orderId, onChanged }: { orderId: number; onChanged: () => void }) {
  const order = useApi(() => api.get<any>(`/api/v1/orders/${orderId}`), [orderId]);
  const action = useAction();
  const [reason, setReason] = useState('');
  const [token, setToken] = useState('tok_visa_approved');
  const o = order.data;

  const setStatus = async (status: string) => {
    if (status === 'cancelled' && !reason) { action.setError(new Error('Enter a cancellation reason first')); return; }
    const r = await action.run(() => api.patch(`/api/v1/orders/${orderId}/status`, { status, reason: reason || undefined }));
    if (r) { void order.reload(); onChanged(); }
  };
  const retryPos = async () => { if (await action.run(() => api.post(`/api/v1/orders/${orderId}/forward-to-pos`))) { void order.reload(); onChanged(); } };
  const takePayment = async () => {
    const outstanding = (Number(o.total) - o.payments.filter((p: any) => ['captured', 'authorised'].includes(p.status))
      .reduce((s: number, p: any) => s + Number(p.amount), 0)).toFixed(2);
    const r = await action.run(() => api.post('/api/v1/payments', { order_id: orderId, amount: outstanding, card_token: token },
      undefined, { 'Idempotency-Key': `ui-${orderId}-${crypto.randomUUID()}` }));
    if (r) { setTimeout(() => { void order.reload(); onChanged(); }, 400); }
  };

  if (order.loading && !o) return <Spinner />;
  if (order.error) return <ErrorBox error={order.error} />;
  return (
    <div className="stack">
      <ErrorBox error={action.error} />
      <div className="grid grid-2">
        <div>
          <div className="stat-row"><span>Status</span><Badge value={o.status} /></div>
          <div className="stat-row"><span>Channel</span><span>{CHANNEL_LABEL[o.channel]}</span></div>
          <div className="stat-row"><span>Branch</span><span>{o.branch_name}</span></div>
          <div className="stat-row"><span>External ref</span><span className="mono small">{o.external_ref ?? '—'}</span></div>
          <div className="stat-row"><span>Simphony check</span><span className="mono small">{o.pos_check_ref ?? '—'}</span></div>
          <div className="stat-row"><span>Customer</span><span>{o.customer ? `${o.customer.name} · ${o.customer.phone}` : 'Walk-in'}</span></div>
          <div className="stat-row"><span>Created</span><span>{dateTime(o.created_at)}</span></div>
          {o.cancel_reason && <div className="stat-row"><span>Cancel reason</span><span>{o.cancel_reason}</span></div>}
        </div>
        <div>
          {o.items.map((i: any) => <div key={i.sku} className="stat-row"><span>{i.quantity} × {i.name}</span><span>{zar(i.line_total)}</span></div>)}
          <div className="stat-row"><span className="muted">Subtotal excl. VAT</span><span>{zar(o.subtotal)}</span></div>
          <div className="stat-row"><span className="muted">VAT (15%)</span><span>{zar(o.vat)}</span></div>
          <div className="stat-row"><strong>Total</strong><strong>{zar(o.total)}</strong></div>
        </div>
      </div>
      <Card title="Payments">
        <DataTable dense rows={o.payments} rowKey={(p: any) => p.id} empty="No payments yet" columns={[
          { key: 'id', header: '#' }, { key: 'provider_reference', header: 'Gateway ref', render: (p: any) => <span className="mono small">{p.provider_reference ?? '—'}</span> },
          { key: 'amount', header: 'Amount', align: 'right', render: (p: any) => zar(p.amount) },
          { key: 'status', header: 'Status', render: (p: any) => <Badge value={p.status} /> },
          { key: 'failure_reason', header: 'Reason', render: (p: any) => <span className="small">{p.failure_reason ?? ''}</span> }]} />
      </Card>
      <div className="row gap-sm wrap">
        {o.status === 'failed' && <Button onClick={retryPos} busy={action.busy}>Retry send to POS</Button>}
        {(NEXT[o.status] ?? []).filter((s) => s !== 'cancelled').map((s) => (
          <Button key={s} variant="secondary" busy={action.busy} onClick={() => setStatus(s)}>Mark {s}</Button>))}
        {!['completed', 'cancelled', 'failed'].includes(o.status) && !o.payments.some((p: any) => p.status === 'captured') && (
          <>
            <select className="input" value={token} onChange={(e) => setToken(e.target.value)} aria-label="Test card">
              {['tok_visa_approved', 'tok_mc_approved', 'tok_declined', 'tok_insufficient_funds', 'tok_expired', 'tok_issuer_unavailable'].map((t) => <option key={t}>{t}</option>)}
            </select>
            <Button onClick={takePayment} busy={action.busy}>Take payment</Button>
          </>)}
      </div>
      {(NEXT[o.status] ?? []).includes('cancelled') && (
        <div className="row gap-sm">
          <input className="input" placeholder="Cancellation reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          <Button variant="danger" busy={action.busy} onClick={() => setStatus('cancelled')}>Cancel order</Button>
        </div>)}
      <details><summary className="muted small">Raw API response</summary><JsonView value={o} /></details>
    </div>
  );
}

export default function Orders() {
  const [filters, setFilters] = useState({ status: '', channel: '', branch_id: '', search: '' });
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const branches = useApi(() => api.get<Branch[]>('/api/v1/branches'), []);
  const list = useApi(() => api.get<Paged<Order>>('/api/v1/orders', { ...filters, limit: PAGE, offset: page * PAGE }),
    [filters, page]);
  const set = (k: string, v: string) => { setPage(0); setFilters({ ...filters, [k]: v }); };

  return (
    <>
      <PageHeader title="Orders" subtitle="Every order across in-store, web, Uber Eats and Mr D"
        actions={<Button onClick={() => setCreating(true)}>+ New in-store order</Button>} />
      <Card>
        <div className="filters">
          <Field label="Search"><input placeholder="Order no. or external ref" value={filters.search} onChange={(e) => set('search', e.target.value)} /></Field>
          <Field label="Status"><select value={filters.status} onChange={(e) => set('status', e.target.value)}>
            <option value="">Any</option>{['received', 'accepted', 'preparing', 'ready', 'completed', 'cancelled', 'failed'].map((s) => <option key={s}>{s}</option>)}</select></Field>
          <Field label="Channel"><select value={filters.channel} onChange={(e) => set('channel', e.target.value)}>
            <option value="">Any</option>{Object.entries(CHANNEL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Branch"><select value={filters.branch_id} onChange={(e) => set('branch_id', e.target.value)}>
            <option value="">All</option>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>
        </div>
        <ErrorBox error={list.error} onRetry={list.reload} />
        {list.loading && !list.data ? <Spinner /> : (
          <DataTable rows={list.data?.items ?? []} rowKey={(o) => o.id} onRowClick={(o) => setSelected(o.id)}
            total={list.data?.total} page={page} pageSize={PAGE} onPage={setPage}
            columns={[
              { key: 'order_number', header: 'Order', render: (o) => <span className="mono">{o.order_number}</span> },
              { key: 'created_at', header: 'Created', render: (o) => dateTime(o.created_at) },
              { key: 'branch_name', header: 'Branch' },
              { key: 'channel', header: 'Channel', render: (o) => CHANNEL_LABEL[o.channel] },
              { key: 'status', header: 'Status', render: (o) => <Badge value={o.status} /> },
              { key: 'payment_status', header: 'Payment', render: (o) => <Badge value={o.payment_status} /> },
              { key: 'total', header: 'Total', align: 'right', render: (o) => zar(o.total), sortValue: (o) => Number(o.total) },
            ]} />
        )}
      </Card>
      <Modal title="Order detail" open={selected !== null} onClose={() => setSelected(null)} wide>
        {selected !== null && <OrderDetail orderId={selected} onChanged={list.reload} />}
      </Modal>
      <Modal title="New in-store order" open={creating} onClose={() => setCreating(false)}>
        <NewOrderForm branches={branches.data ?? []} onCreated={(msg, id) => { setCreating(false); setToast(msg); void list.reload(); setSelected(id); }} />
      </Modal>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}

const MENU = [['CHK-QTR', 'Quarter Chicken & Chips', 69.9], ['CHK-HLF', 'Half Chicken & Chips', 104.9], ['CHK-FUL', 'Full Chicken', 164.9],
  ['BRG-PRI', 'Peri-Peri Prego Burger', 84.9], ['WRP-CHK', 'Grilled Chicken Wrap', 69.9], ['MEAL-FAM', 'Family Feast', 359.9],
  ['SIDE-CHP', 'Regular Chips', 29.9], ['SIDE-PAP', 'Pap & Chakalaka', 27.9], ['DRK-CAN', 'Soft Drink 330ml', 21.9]] as const;

function NewOrderForm({ branches, onCreated }: { branches: Branch[]; onCreated: (msg: string, id: number) => void }) {
  const [branchId, setBranchId] = useState('');
  const [phone, setPhone] = useState('');
  const [qty, setQty] = useState<Record<string, number>>({});
  const action = useAction();
  const items = Object.entries(qty).filter(([, q]) => q > 0).map(([sku, quantity]) => ({ sku, quantity }));
  const total = MENU.reduce((s, [sku, , p]) => s + (qty[sku] ?? 0) * p, 0);
  const phoneOk = !phone || /^0\d{9}$/.test(phone);

  const submit = async () => {
    if (!branchId || !items.length || !phoneOk) { action.setError(new Error('Choose a branch, at least one item and a valid phone (optional)')); return; }
    const r = await action.run(() => api.post<any>('/api/v1/orders', { branch_id: Number(branchId), channel: 'in_store',
      customer_phone: phone || undefined, items }));
    if (r) onCreated(`${r.order.order_number}: ${r.message}`, r.order.id);
  };
  return (
    <div className="stack">
      <ErrorBox error={action.error} />
      <div className="form-grid">
        <Field label="Branch"><select value={branchId} onChange={(e) => setBranchId(e.target.value)}><option value="">Select…</option>
          {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>
        <Field label="Customer phone (loyalty)" error={phoneOk ? undefined : '10 digits, starting with 0'}>
          <input value={phone} placeholder="0821234567" onChange={(e) => setPhone(e.target.value)} /></Field>
      </div>
      <div>{MENU.map(([sku, name, price]) => (
        <div key={sku} className="stat-row"><span>{name} <span className="muted small">{zar(price)}</span></span>
          <input className="input" type="number" min={0} max={20} style={{ width: 70 }} aria-label={`Quantity ${name}`}
                 value={qty[sku] ?? 0} onChange={(e) => setQty({ ...qty, [sku]: Math.max(0, Number(e.target.value)) })} /></div>))}</div>
      <div className="stat-row"><strong>Total (incl. VAT)</strong><strong>{zar(total)}</strong></div>
      <div className="form-actions"><Button busy={action.busy} onClick={submit}>Create & send to POS</Button></div>
    </div>
  );
}
