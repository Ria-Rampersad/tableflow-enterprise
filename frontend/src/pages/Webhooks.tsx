import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, JsonView, Modal, PageHeader, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Paged, WebhookEvent } from '../services/types';
import { dateTime } from '../utils/format';

const PAGE = 25;

export default function Webhooks() {
  const [params] = useSearchParams();
  const [source, setSource] = useState('');
  const [status, setStatus] = useState(params.get('status') ?? '');
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<WebhookEvent | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [subOpen, setSubOpen] = useState(false);
  const events = useApi(() => api.get<Paged<WebhookEvent>>('/api/v1/webhooks/events', { source, status, limit: PAGE, offset: page * PAGE }), [source, status, page]);
  const subs = useApi(() => api.get<any[]>('/api/v1/webhooks/subscriptions'), []);
  const action = useAction();

  const replay = async (e: WebhookEvent) => {
    const r = await action.run(() => api.post<WebhookEvent>(`/api/v1/webhooks/events/${e.id}/replay`));
    if (r) { setSelected(r); setToast(`Replay result: ${r.status}`); void events.reload(); }
  };
  const forged = async () => {
    const r = await action.run(() => api.post<any>('/api/v1/simulate/bad-signature-webhook'));
    if (r) { setToast(`Forged webhook → HTTP ${r.http_status} (${r.event_status}: ${r.error})`); void events.reload(); }
  };

  return (
    <>
      <PageHeader title="Webhook Management" subtitle="Inbound provider events: HMAC signature verification, de-duplication, processing, replay"
        actions={<Button variant="secondary" busy={action.busy} onClick={forged}>Send forged webhook (security demo)</Button>} />
      <div className="alert alert-info"><div>Inbound endpoints: <code>POST /api/v1/webhooks/inbound/transaction-junction</code> (<code>X-TJ-Signature: t=…,v1=…</code>), <code>/uber-eats</code> (<code>X-Uber-Signature</code>), <code>/mr-d</code> (<code>X-MrD-Signature</code>). Duplicates on (source, event_id) are acknowledged but not re-processed.</div></div>
      <ErrorBox error={events.error || action.error} />
      <Card title="Event history">
        <div className="filters">
          <Field label="Source"><select value={source} onChange={(e) => { setPage(0); setSource(e.target.value); }}>
            <option value="">All</option><option value="transaction_junction">Transaction Junction</option><option value="uber_eats">Uber Eats</option><option value="mr_d">Mr D</option></select></Field>
          <Field label="Status"><select value={status} onChange={(e) => { setPage(0); setStatus(e.target.value); }}>
            <option value="">All</option>{['processed', 'failed', 'rejected', 'received'].map((s) => <option key={s}>{s}</option>)}</select></Field>
        </div>
        <DataTable rows={events.data?.items ?? []} rowKey={(e) => e.id} onRowClick={setSelected} total={events.data?.total}
          page={page} pageSize={PAGE} onPage={setPage} columns={[
            { key: 'received_at', header: 'Received', render: (e) => dateTime(e.received_at) },
            { key: 'source', header: 'Source' },
            { key: 'event_type', header: 'Type', render: (e) => <span className="mono small">{e.event_type}</span> },
            { key: 'event_id', header: 'Event ID', render: (e) => <span className="mono small">{e.event_id}</span> },
            { key: 'signature_valid', header: 'Signature', render: (e) => <Badge value={e.signature_valid ? 'valid' : 'invalid'} tone={e.signature_valid ? 'good' : 'bad'} /> },
            { key: 'attempts', header: 'Deliveries', align: 'right' },
            { key: 'status', header: 'Status', render: (e) => <Badge value={e.status} /> },
            { key: 'error', header: 'Error', render: (e) => <span className="small">{e.error ?? ''}</span> },
          ]} />
      </Card>
      <Card title="Outbound subscriptions" subtitle="Registered targets (e.g. n8n workflows) and the events they receive" className="mt"
            actions={<Button variant="secondary" onClick={() => setSubOpen(true)}>Register</Button>}>
        <DataTable dense rows={subs.data ?? []} rowKey={(s: any) => s.id} columns={[
          { key: 'name', header: 'Name' }, { key: 'target_url', header: 'Target', render: (s: any) => <span className="mono small">{s.target_url}</span> },
          { key: 'event_types', header: 'Events', render: (s: any) => <div className="chip-list">{s.event_types.map((e: string) => <Badge key={e} value={e} tone="info" />)}</div> },
          { key: 'is_active', header: 'Active', render: (s: any) => <Badge value={s.is_active ? 'healthy' : 'disabled'} /> }]} />
      </Card>
      <Modal title={`Event ${selected?.event_id}`} open={!!selected} onClose={() => setSelected(null)} wide>
        {selected && (<div className="stack">
          <div className="row gap-sm"><Badge value={selected.status} /> <span className="muted small">{selected.attempts} delivery attempt(s)</span>
            {selected.status === 'failed' && <Button busy={action.busy} onClick={() => replay(selected)}>Replay event</Button>}</div>
          {selected.error && <div className="alert alert-error">{selected.error}</div>}
          <JsonView value={selected.payload} /></div>)}
      </Modal>
      <Modal title="Register webhook subscription" open={subOpen} onClose={() => setSubOpen(false)}>
        <SubscriptionForm onSaved={() => { setSubOpen(false); setToast('Subscription registered'); void subs.reload(); }} />
      </Modal>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}

function SubscriptionForm({ onSaved }: { onSaved: () => void }) {
  const [f, setF] = useState({ name: '', target_url: 'https://', event_types: 'payment.failed' });
  const action = useAction();
  const urlOk = /^https?:\/\/.+/.test(f.target_url);
  const save = async () => {
    if (f.name.length < 3 || !urlOk) { action.setError(new Error('Name (3+ chars) and a valid http(s) URL are required')); return; }
    if (await action.run(() => api.post('/api/v1/webhooks/subscriptions', { ...f, event_types: f.event_types.split(',').map((s) => s.trim()).filter(Boolean) }))) onSaved();
  };
  return (<div className="stack">
    <ErrorBox error={action.error} />
    <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
    <Field label="Target URL" error={urlOk ? undefined : 'Must start with http:// or https://'}><input value={f.target_url} onChange={(e) => setF({ ...f, target_url: e.target.value })} /></Field>
    <Field label="Event types (comma separated)" hint="payment.failed, order.received, incident.created …"><input value={f.event_types} onChange={(e) => setF({ ...f, event_types: e.target.value })} /></Field>
    <div className="form-actions"><Button busy={action.busy} onClick={save}>Register</Button></div>
  </div>);
}
