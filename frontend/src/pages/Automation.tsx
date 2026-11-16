import { useState } from 'react';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, JsonView, PageHeader } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Branch, Notification, Paged } from '../services/types';
import { dateTime, isoDay } from '../utils/format';

const WORKFLOWS = [
  ['01', 'Failed payment notifications', 'Webhook ← payment.failed', 'Alert finance; raise incident if ≥ R500'],
  ['02', 'Failed POS integrations', 'Webhook ← pos.*_failed', 'Check POS status; incident if ≥ 3 orders stuck'],
  ['03', 'New order processing', 'Webhook ← order.received', 'Alert branch on large digital orders'],
  ['04', 'Loyalty point updates', 'Webhook ← loyalty.*', 'Auto-retry failed loyalty syncs'],
  ['05', 'Daily financial reconciliation', 'Schedule 06:00 SAST', 'Run recon, post summary to finance'],
  ['06', 'Low-stock notifications', 'Schedule every 3h', 'Group low stock per branch → procurement'],
  ['07', 'Incident escalation', 'Webhook ← incident.*', 'Page on-call for SEV1; auto-escalate after 30 min'],
  ['08', 'Daily management reporting', 'Schedule Mon–Sat 07:00', 'Sales, payments, integrations, incidents digest'],
];

export default function Automation() {
  const [output, setOutput] = useState<{ title: string; data: unknown } | null>(null);
  const [workflow, setWorkflow] = useState('');
  const [day, setDay] = useState(isoDay(-1));
  const [branch, setBranch] = useState('');
  const branches = useApi(() => api.get<Branch[]>('/api/v1/branches'), []);
  const notes = useApi(() => api.get<Paged<Notification>>('/api/v1/notifications', { workflow, limit: 30 }), [workflow]);
  const action = useAction();

  const run = async (title: string, fn: () => Promise<unknown>) => {
    const data = await action.run(fn);
    if (data) { setOutput({ title, data }); void notes.reload(); }
  };

  return (
    <>
      <PageHeader title="Internal Automation Tools" subtitle="Operational tools for finance and operations — the same endpoints the n8n workflows call" />
      <ErrorBox error={action.error} />
      <div className="grid grid-3">
        <Card title="Run a tool" className="span-2">
          <div className="filters">
            <label className="field"><span>Business date</span><input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></label>
            <label className="field"><span>Branch (journal)</span><select value={branch} onChange={(e) => setBranch(e.target.value)}>
              <option value="">Select…</option>{branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          </div>
          <div className="row gap-sm wrap">
            <Button busy={action.busy} onClick={() => run('Daily sales summary', () => api.get('/api/v1/automation/daily-summary', { business_date: day }))}>Daily sales summary</Button>
            <Button busy={action.busy} onClick={() => run('Payment reconciliation', () => api.post('/api/v1/automation/daily-reconciliation', undefined, { business_date: day }))}>Run reconciliation</Button>
            <Button busy={action.busy} variant="secondary" onClick={() => run('Order discrepancy detection', () => api.post('/api/v1/automation/discrepancy-scan', undefined, { raise_incident: true }))}>Discrepancy scan (+incident)</Button>
            <Button busy={action.busy} variant="secondary" onClick={() => run('Integration health check', () => api.post('/api/v1/automation/integration-health-check'))}>Integration health check</Button>
            <Button busy={action.busy} variant="secondary" onClick={() => run('Low stock', () => api.get('/api/v1/automation/low-stock'))}>Low-stock report</Button>
            <Button busy={action.busy} variant="secondary" disabled={!branch} onClick={() => run('Finance GL journal', () => api.post(`/api/v1/automation/finance-journal/${branch}`, undefined, { business_date: day }))}>Post finance journal</Button>
            <Button busy={action.busy} variant="ghost" onClick={() => run('Branch performance', () => api.get('/api/v1/reports/branch-performance', { start: day, end: day }))}>Branch performance</Button>
          </div>
          {output && <div className="mt"><h3>{output.title}</h3><JsonView value={output.data} /></div>}
        </Card>
        <Card title="n8n workflows" subtitle="Importable JSON in automation/n8n">
          {WORKFLOWS.map(([n, name, trigger, what]) => (
            <div key={n} className="stat-row"><span><strong>{n}</strong> {name}<div className="muted small">{trigger} → {what}</div></span></div>))}
        </Card>
      </div>
      <Card title="Notification outbox" subtitle="Events queued for n8n (status 'recorded' = n8n URL not configured; 'delivered' = alert received from n8n)" className="mt"
            actions={<select className="input" value={workflow} onChange={(e) => setWorkflow(e.target.value)} aria-label="Workflow">
              <option value="">All workflows</option>{['failed_payment', 'pos_failure', 'new_order', 'loyalty_update', 'incident_escalation', 'n8n_alert'].map((w) => <option key={w}>{w}</option>)}</select>}>
        <DataTable dense rows={notes.data?.items ?? []} rowKey={(n) => n.id} columns={[
          { key: 'created_at', header: 'Time', render: (n) => dateTime(n.created_at) },
          { key: 'workflow', header: 'Workflow' }, { key: 'event_type', header: 'Event', render: (n) => <span className="mono small">{n.event_type}</span> },
          { key: 'status', header: 'Status', render: (n) => <Badge value={n.status} /> },
          { key: 'payload', header: 'Payload', render: (n) => <span className="small mono">{String((n.payload as any).text ?? JSON.stringify(n.payload)).slice(0, 140)}</span> },
        ]} />
      </Card>
    </>
  );
}
