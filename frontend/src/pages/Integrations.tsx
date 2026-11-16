import { useState } from 'react';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, JsonView, Modal, PageHeader, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api, session } from '../services/api';
import type { Integration, IntegrationLog, Paged } from '../services/types';
import { dateTime, num, pct, titleCase } from '../utils/format';

export default function Integrations() {
  const list = useApi(() => api.get<Integration[]>('/api/v1/integrations'), []);
  const failed = useApi(() => api.get<Paged<IntegrationLog>>('/api/v1/integrations/logs/failed', { limit: 20 }), []);
  const [logsFor, setLogsFor] = useState<Integration | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const action = useAction();
  const canConfigure = ['admin', 'integration_engineer'].includes(session.user()?.role ?? '');
  const refresh = () => { void list.reload(); void failed.reload(); };

  const check = async (i: Integration) => {
    const r = await action.run(() => api.post<any>(`/api/v1/integrations/${i.id}/health-check`));
    if (r) { setToast(`${i.display_name}: ${r.ok ? 'reachable' : `FAILED – ${r.error}`}`); refresh(); }
  };
  const configure = async (i: Integration, body: Record<string, unknown>) => {
    if (await action.run(() => api.patch(`/api/v1/integrations/${i.id}`, body))) refresh();
  };
  const retry = async (l: IntegrationLog) => {
    const r = await action.run(() => api.post<any>(`/api/v1/integrations/logs/${l.id}/retry`));
    if (r) { setToast(`Retried ${r.retried}: ${r.ok ? 'success' : 'still failing'}`); refresh(); }
  };

  return (
    <>
      <PageHeader title="Integration Monitoring" subtitle="Status, latency, failures and retries for every connected system"
        actions={<Button variant="secondary" onClick={refresh}>Refresh</Button>} />
      <ErrorBox error={list.error || action.error} />
      {list.loading && !list.data ? <Spinner /> : (
        <div className="health-grid">
          {list.data!.map((i) => {
            const availability = i.total_requests ? (1 - i.total_failures / i.total_requests) * 100 : 100;
            return (
              <Card key={i.id} title={<><span className={`dot dot-${i.status}`} />{i.display_name}</>} subtitle={`${titleCase(i.kind)} · ${i.provider}`}
                    actions={<Badge value={i.status} />}>
                <div className="stat-row"><span>Mode</span><Badge value={i.mode} /></div>
                <div className="stat-row"><span>Last success</span><span>{dateTime(i.last_success_at)}</span></div>
                <div className="stat-row"><span>Last failure</span><span>{dateTime(i.last_failure_at)}</span></div>
                <div className="stat-row"><span>Avg response</span><span>{i.avg_response_ms} ms</span></div>
                <div className="stat-row"><span>Requests / failed</span><span>{num(i.total_requests)} / {num(i.total_failures)}</span></div>
                <div className="stat-row"><span>Availability</span><span>{pct(availability, 2)}</span></div>
                <div className="stat-row"><span>Consecutive failures</span><span>{i.consecutive_failures}</span></div>
                {i.last_error && <p className="small muted">Last error: {i.last_error}</p>}
                <div className="row gap-sm wrap mt">
                  <Button variant="secondary" busy={action.busy} onClick={() => check(i)}>Health check</Button>
                  <Button variant="ghost" onClick={() => setLogsFor(i)}>Logs</Button>
                  {canConfigure && (i.config.simulate_outage
                    ? <Button variant="primary" busy={action.busy} onClick={() => configure(i, { simulate_outage: false, status: 'healthy' })}>End outage</Button>
                    : <Button variant="danger" busy={action.busy} onClick={() => configure(i, { simulate_outage: true })}>Simulate outage</Button>)}
                </div>
                {canConfigure && (
                  <label className="field mt">
                    <span>Random failure rate: {Math.round((i.config.failure_rate ?? 0) * 100)}%</span>
                    <input type="range" min={0} max={0.5} step={0.05} value={i.config.failure_rate ?? 0}
                           onChange={(e) => configure(i, { failure_rate: Number(e.target.value) })} />
                  </label>)}
              </Card>);
          })}
        </div>)}
      <Card title="Failed integration calls" subtitle="Retry re-runs the business operation (POS check, loyalty sync, menu/transaction sync)" className="mt">
        <DataTable dense rows={failed.data?.items ?? []} rowKey={(l) => l.id} empty="No failed calls" columns={[
          { key: 'created_at', header: 'Time', render: (l) => dateTime(l.created_at) },
          { key: 'integration', header: 'Integration', render: (l) => list.data?.find((i) => i.id === l.integration_id)?.display_name },
          { key: 'operation', header: 'Operation' },
          { key: 'entity', header: 'Entity', render: (l) => l.entity_type ? `${l.entity_type} #${l.entity_id}` : '—' },
          { key: 'http_status', header: 'HTTP', align: 'right' },
          { key: 'error_message', header: 'Error', render: (l) => <span className="small">{l.error_message}</span> },
          { key: 'act', header: '', render: (l) => ['create_check', 'loyalty_earn', 'menu_sync', 'transaction_sync'].includes(l.operation) &&
            <Button variant="secondary" busy={action.busy} onClick={() => retry(l)}>Retry</Button> },
        ]} />
      </Card>
      <Modal title={`${logsFor?.display_name} logs`} open={!!logsFor} onClose={() => setLogsFor(null)} wide>
        {logsFor && <LogTable integrationId={logsFor.id} />}
      </Modal>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}

function LogTable({ integrationId }: { integrationId: number }) {
  const [status, setStatus] = useState('');
  const [open, setOpen] = useState<IntegrationLog | null>(null);
  const logs = useApi(() => api.get<Paged<IntegrationLog>>(`/api/v1/integrations/${integrationId}/logs`, { status, limit: 50 }), [integrationId, status]);
  return (
    <>
      <div className="filters"><select className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
        <option value="">All</option><option>success</option><option>failed</option><option>retrying</option><option>retried_ok</option></select>
        <span className="muted small">{logs.data?.total ?? 0} entries</span></div>
      <DataTable dense rows={logs.data?.items ?? []} rowKey={(l) => l.id} onRowClick={setOpen} columns={[
        { key: 'created_at', header: 'Time', render: (l) => dateTime(l.created_at) }, { key: 'operation', header: 'Operation' },
        { key: 'status', header: 'Status', render: (l) => <Badge value={l.status} /> }, { key: 'attempt', header: 'Try', align: 'right' },
        { key: 'response_ms', header: 'ms', align: 'right' }, { key: 'correlation_id', header: 'Correlation', render: (l) => <span className="mono small">{l.correlation_id}</span> }]} />
      {open && <div className="mt"><JsonView value={open} /></div>}
    </>
  );
}
