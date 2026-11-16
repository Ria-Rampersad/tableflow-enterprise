import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, Modal, PageHeader, SimulatedTag, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api, session } from '../services/api';
import type { Paged, Payment } from '../services/types';
import { dateTime, zar } from '../utils/format';

const PAGE = 25;

export default function Payments() {
  const [params, setParams] = useSearchParams();
  const status = params.get('status') ?? '';
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Payment | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const list = useApi(() => api.get<Paged<Payment>>('/api/v1/payments', { status, limit: PAGE, offset: page * PAGE }), [status, page]);
  const isFinance = ['finance', 'admin'].includes(session.user()?.role ?? '');

  return (
    <>
      <PageHeader title="Payment Integration Hub" subtitle={<>Transaction Junction-style gateway: authorise → webhook capture → settle, refunds <SimulatedTag /></>}
        actions={<div className="row gap-sm">{['', 'captured', 'authorised', 'failed', 'refunded', 'partially_refunded'].map((s) => (
          <Button key={s || 'all'} variant={s === status ? 'primary' : 'secondary'} onClick={() => { setPage(0); setParams(s ? { status: s } : {}); }}>{s ? s.replace('_', ' ') : 'All'}</Button>))}</div>} />
      <div className="alert alert-info"><div>Test card tokens: <code>tok_visa_approved</code>, <code>tok_declined</code> (05), <code>tok_insufficient_funds</code> (51), <code>tok_expired</code> (54), <code>tok_issuer_unavailable</code> (91, retried). Take payments from an order's detail screen.</div></div>
      <Card>
        <ErrorBox error={list.error} onRetry={list.reload} />
        {list.loading && !list.data ? <Spinner /> : (
          <DataTable rows={list.data?.items ?? []} rowKey={(p) => p.id} total={list.data?.total} page={page} pageSize={PAGE}
            onPage={setPage} onRowClick={setSelected} columns={[
              { key: 'id', header: '#' },
              { key: 'created_at', header: 'Time', render: (p) => dateTime(p.created_at) },
              { key: 'provider_reference', header: 'Gateway reference', render: (p) => <span className="mono small">{p.provider_reference ?? '—'}</span> },
              { key: 'order_id', header: 'Order #' },
              { key: 'method', header: 'Method' },
              { key: 'status', header: 'Status', render: (p) => <Badge value={p.status} /> },
              { key: 'failure_reason', header: 'Failure reason', render: (p) => <span className="small">{p.failure_reason ?? ''}</span> },
              { key: 'amount', header: 'Amount', align: 'right', render: (p) => zar(p.amount), sortValue: (p) => Number(p.amount) },
            ]} />)}
      </Card>
      <Modal title={`Payment #${selected?.id}`} open={!!selected} onClose={() => setSelected(null)}>
        {selected && <PaymentDetail payment={selected} canRefund={isFinance} onDone={(m) => { setToast(m); setSelected(null); void list.reload(); }} />}
      </Modal>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}

function PaymentDetail({ payment, canRefund, onDone }: { payment: Payment; canRefund: boolean; onDone: (msg: string) => void }) {
  const refunds = useApi(() => api.get<any[]>(`/api/v1/payments/${payment.id}/refunds`), [payment.id]);
  const remaining = Number(payment.amount) - Number(payment.refunded_amount);
  const [amount, setAmount] = useState(remaining.toFixed(2));
  const [reason, setReason] = useState('');
  const action = useAction();
  const amountErr = Number(amount) <= 0 || Number(amount) > remaining ? `Between R0.01 and ${zar(remaining)}` : undefined;

  const refund = async () => {
    if (amountErr || reason.length < 3) { action.setError(new Error('Enter a valid amount and a reason (min 3 characters)')); return; }
    const r = await action.run(() => api.post(`/api/v1/payments/${payment.id}/refunds`, { amount, reason }));
    if (r) onDone(`Refund of ${zar(amount)} completed`);
  };
  const callback = async () => {
    const r = await action.run(() => api.post<any>(`/api/v1/payments/${payment.id}/simulate-callback`));
    if (r) onDone(`Gateway webhook ${r.status}: payment now ${r.payment_status}`);
  };

  return (
    <div className="stack">
      <ErrorBox error={action.error} />
      <div className="stat-row"><span>Status</span><Badge value={payment.status} /></div>
      <div className="stat-row"><span>Amount</span><span>{zar(payment.amount)}</span></div>
      <div className="stat-row"><span>Refunded</span><span>{zar(payment.refunded_amount)}</span></div>
      <div className="stat-row"><span>Gateway ref</span><span className="mono small">{payment.provider_reference}</span></div>
      <div className="stat-row"><span>Idempotency key</span><span className="mono small">{(payment as any).idempotency_key}</span></div>
      {payment.status === 'authorised' && <Button variant="secondary" busy={action.busy} onClick={callback}>Simulate gateway "captured" webhook</Button>}
      {refunds.data && refunds.data.length > 0 && (
        <Card title="Refunds"><DataTable dense rows={refunds.data} rowKey={(r: any) => r.id} columns={[
          { key: 'amount', header: 'Amount', render: (r: any) => zar(r.amount) }, { key: 'reason', header: 'Reason' },
          { key: 'status', header: 'Status', render: (r: any) => <Badge value={r.status} /> }, { key: 'created_at', header: 'When', render: (r: any) => dateTime(r.created_at) }]} /></Card>)}
      {canRefund && ['captured', 'partially_refunded'].includes(payment.status) && (
        <Card title="Issue refund" subtitle="Finance only · audit logged">
          <div className="form-grid">
            <Field label="Amount (ZAR)" error={amountErr}><input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
            <Field label="Reason"><input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Missing item" /></Field>
          </div>
          <div className="form-actions"><Button variant="danger" busy={action.busy} onClick={refund}>Refund</Button></div>
        </Card>)}
    </div>
  );
}
