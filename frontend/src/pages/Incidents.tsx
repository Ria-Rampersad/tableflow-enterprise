import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, Kpi, Modal, PageHeader, Spinner } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Incident, Paged } from '../services/types';
import { dateTime, titleCase } from '../utils/format';

export default function Incidents() {
  const navigate = useNavigate();
  const [openOnly, setOpenOnly] = useState(true);
  const [severity, setSeverity] = useState('');
  const [creating, setCreating] = useState(false);
  const list = useApi(() => api.get<Paged<Incident>>('/api/v1/incidents', { open_only: openOnly, severity, limit: 100 }), [openOnly, severity]);
  const report = useApi(() => api.get<any>('/api/v1/incidents/report', {}), []);

  return (
    <>
      <PageHeader title="Incident Management" subtitle="Payment gateway downtime, POS sync failures, reconciliation variances — tracked to resolution"
        actions={<Button onClick={() => setCreating(true)}>+ Report incident</Button>} />
      {report.data && (
        <div className="grid grid-kpi">
          <Kpi label="Incidents (30d)" value={report.data.total} />
          <Kpi label="Resolved" value={report.data.resolved} tone="good" />
          <Kpi label="Automated detections" value={report.data.automated} hint="raised by monitoring" />
          {report.data.by_severity.map((s: any) => (
            <Kpi key={s.severity} label={`${s.severity} MTTR`} value={s.mttr_minutes ? `${Math.round(s.mttr_minutes)} min` : '—'} hint={`${s.opened} opened`} tone={s.severity === 'SEV1' ? 'bad' : 'default'} />))}
        </div>)}
      <Card className="mt">
        <div className="filters">
          <label className="checks"><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open only</label>
          <select className="input" value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severity">
            <option value="">All severities</option>{['SEV1', 'SEV2', 'SEV3', 'SEV4'].map((s) => <option key={s}>{s}</option>)}</select>
        </div>
        <ErrorBox error={list.error} onRetry={list.reload} />
        {list.loading && !list.data ? <Spinner /> : (
          <DataTable rows={list.data?.items ?? []} rowKey={(i) => i.id} onRowClick={(i) => navigate(`/incidents/${i.id}`)} empty="No incidents match"
            columns={[
              { key: 'reference', header: 'Ref', render: (i) => <span className="mono">{i.reference}</span> },
              { key: 'severity', header: 'Sev', render: (i) => <Badge value={i.severity} /> },
              { key: 'title', header: 'Title', render: (i) => <strong>{i.title}</strong> },
              { key: 'category', header: 'Category', render: (i) => titleCase(i.category) },
              { key: 'source', header: 'Source', render: (i) => <Badge value={i.source} tone={i.source === 'automated' ? 'info' : 'neutral'} /> },
              { key: 'status', header: 'Status', render: (i) => <Badge value={i.status} /> },
              { key: 'escalation_level', header: 'Esc.', align: 'right' },
              { key: 'opened_at', header: 'Opened', render: (i) => dateTime(i.opened_at) },
            ]} />)}
      </Card>
      <Modal title="Report incident" open={creating} onClose={() => setCreating(false)}>
        <NewIncident onCreated={(id) => navigate(`/incidents/${id}`)} />
      </Modal>
    </>
  );
}

function NewIncident({ onCreated }: { onCreated: (id: number) => void }) {
  const [f, setF] = useState({ title: '', description: '', severity: 'SEV3', category: 'pos' });
  const action = useAction();
  const titleErr = f.title.length > 0 && f.title.length < 5 ? 'At least 5 characters' : undefined;
  const save = async () => {
    if (f.title.length < 5) { action.setError(new Error('Title must be at least 5 characters')); return; }
    const r = await action.run(() => api.post<Incident>('/api/v1/incidents', f));
    if (r) onCreated(r.id);
  };
  return (
    <div className="stack">
      <ErrorBox error={action.error} />
      <Field label="Title" error={titleErr}><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="e.g. Card payments failing at Rosebank" /></Field>
      <div className="form-grid">
        <Field label="Severity" hint="SEV1 = trading stopped / money at risk"><select value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}>{['SEV1', 'SEV2', 'SEV3', 'SEV4'].map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="Category"><select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
          {['payment', 'pos', 'ordering', 'loyalty', 'reconciliation', 'infrastructure', 'other'].map((c) => <option key={c}>{c}</option>)}</select></Field>
      </div>
      <Field label="Description"><textarea rows={4} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      <div className="form-actions"><Button busy={action.busy} onClick={save}>Create incident</Button></div>
    </div>
  );
}
