import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, Button, Card, ErrorBox, Field, PageHeader, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Incident } from '../services/types';
import { dateTime, titleCase } from '../utils/format';

const NEXT: Record<string, string[]> = {
  open: ['investigating', 'mitigated', 'resolved'], investigating: ['mitigated', 'resolved'],
  mitigated: ['resolved', 'investigating'], resolved: ['closed', 'investigating'], closed: [],
};

export default function IncidentDetail() {
  const { id } = useParams();
  const inc = useApi(() => api.get<Incident>(`/api/v1/incidents/${id}`), [id]);
  const users = useApi(() => api.get<any[]>('/api/v1/auth/users').catch(() => []), []);
  const [note, setNote] = useState('');
  const [rca, setRca] = useState({ root_cause: '', resolution_notes: '' });
  const [toast, setToast] = useState<string | null>(null);
  const action = useAction();
  const i = inc.data;

  const update = async (body: Record<string, unknown>, msg: string) => {
    const r = await action.run(() => api.patch<Incident>(`/api/v1/incidents/${id}`, body));
    if (r) { inc.setData(r); setToast(msg); }
  };
  const escalate = async () => {
    const r = await action.run(() => api.post<Incident>(`/api/v1/incidents/${id}/escalate`, { reason: note || 'Manual escalation' }));
    if (r) { inc.setData(r); setNote(''); setToast(`Escalated to level ${r.escalation_level}`); }
  };
  const addNote = async () => {
    if (note.length < 2) return;
    const r = await action.run(() => api.post<Incident>(`/api/v1/incidents/${id}/notes`, { message: note }));
    if (r) { inc.setData(r); setNote(''); }
  };

  if (inc.loading && !i) return <Spinner />;
  if (!i) return <ErrorBox error={inc.error} />;
  const resolving = ['resolved', 'closed'];

  return (
    <>
      <PageHeader title={`${i.reference} · ${i.title}`}
        subtitle={<><Link to="/incidents">Incidents</Link> · {titleCase(i.category)} · opened {dateTime(i.opened_at)} · source {i.source}</>}
        actions={<><Badge value={i.severity} /><Badge value={i.status} /></>} />
      <ErrorBox error={action.error} />
      <div className="grid grid-3">
        <div className="span-2 stack">
          <Card title="Description"><p>{i.description || <span className="muted">No description</span>}</p></Card>
          <Card title="Root-cause analysis & resolution" subtitle="Required before an incident can be resolved">
            {i.root_cause || i.resolution_notes ? (
              <><div className="stat-row"><span>Root cause</span><span>{i.root_cause ?? '—'}</span></div>
                <div className="stat-row"><span>Resolution</span><span>{i.resolution_notes ?? '—'}</span></div>
                <div className="stat-row"><span>Resolved at</span><span>{dateTime(i.resolved_at)}</span></div></>
            ) : null}
            {!resolving.includes(i.status) && (
              <div className="stack mt">
                <Field label="Root cause (5 whys → underlying cause)"><textarea rows={2} value={rca.root_cause} onChange={(e) => setRca({ ...rca, root_cause: e.target.value })} /></Field>
                <Field label="Resolution notes & prevention actions"><textarea rows={3} value={rca.resolution_notes} onChange={(e) => setRca({ ...rca, resolution_notes: e.target.value })} /></Field>
                <div className="form-actions"><Button busy={action.busy} disabled={!rca.resolution_notes}
                  onClick={() => update({ status: 'resolved', ...rca }, 'Incident resolved')}>Resolve incident</Button></div>
              </div>)}
          </Card>
          <Card title="Timeline & escalation history">
            <ul className="timeline">{i.events?.map((e) => (
              <li key={e.id}><div className="row gap-sm"><Badge value={e.event_type} tone={e.event_type === 'escalation' ? 'bad' : 'info'} /><span className="muted small">{dateTime(e.created_at)} · {e.actor}</span></div><div>{e.message}</div></li>))}</ul>
            <div className="row gap-sm mt">
              <input className="input" style={{ flex: 1 }} placeholder="Add an update or escalation reason" value={note} onChange={(e) => setNote(e.target.value)} />
              <Button variant="secondary" busy={action.busy} onClick={addNote}>Add note</Button>
            </div>
          </Card>
        </div>
        <Card title="Actions">
          <div className="stack">
            <Field label="Assign to"><select value={i.assigned_to_id ?? ''} onChange={(e) => update({ assigned_to_id: Number(e.target.value) }, 'Assigned')}>
              <option value="">Unassigned</option>{users.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
            <Field label="Severity"><select value={i.severity} onChange={(e) => update({ severity: e.target.value }, 'Severity updated')}>
              {['SEV1', 'SEV2', 'SEV3', 'SEV4'].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <div className="row gap-sm wrap">{NEXT[i.status].filter((s) => s !== 'resolved').map((s) => (
              <Button key={s} variant="secondary" busy={action.busy} onClick={() => update({ status: s, resolution_notes: s === 'closed' ? i.resolution_notes : undefined }, `Moved to ${s}`)}>→ {s}</Button>))}</div>
            {!resolving.includes(i.status) && <Button variant="danger" busy={action.busy} onClick={escalate}>Escalate (level {i.escalation_level + 1})</Button>}
            <p className="muted small">Escalation path: L1 Solutions Engineering lead → L2 Head of Engineering → L3 CTO / vendor executive. SEV1/SEV2 notify n8n workflow 07.</p>
          </div>
        </Card>
      </div>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}
