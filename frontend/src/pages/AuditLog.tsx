import { useState } from 'react';
import { DataTable } from '../components/DataTable';
import { Card, ErrorBox, Field, JsonView, PageHeader, Spinner } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Paged } from '../services/types';
import { dateTime } from '../utils/format';

const PAGE = 50;

export default function AuditLog() {
  const [entity, setEntity] = useState('');
  const [actor, setActor] = useState('');
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<any>(null);
  const logs = useApi(() => api.get<Paged<any>>('/api/v1/audit-logs', { entity_type: entity, actor, limit: PAGE, offset: page * PAGE }), [entity, actor, page]);
  return (
    <>
      <PageHeader title="Audit Trail" subtitle="Append-only record of every state change (enforced by a PostgreSQL trigger)" />
      <Card>
        <div className="filters">
          <Field label="Entity"><select value={entity} onChange={(e) => { setPage(0); setEntity(e.target.value); }}><option value="">All</option>
            {['order', 'payment', 'refund', 'branch', 'incident', 'integration', 'reconciliation_run', 'loyalty_account', 'user', 'webhook_event'].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Actor"><input value={actor} onChange={(e) => { setPage(0); setActor(e.target.value); }} placeholder="email or partner:uber_eats" /></Field>
        </div>
        <ErrorBox error={logs.error} />
        {logs.loading && !logs.data ? <Spinner /> : (
          <DataTable dense rows={logs.data?.items ?? []} rowKey={(a) => a.id} onRowClick={setOpen} total={logs.data?.total} page={page} pageSize={PAGE} onPage={setPage}
            columns={[
              { key: 'created_at', header: 'Time', render: (a) => dateTime(a.created_at) },
              { key: 'actor', header: 'Actor' }, { key: 'action', header: 'Action', render: (a) => <span className="mono small">{a.action}</span> },
              { key: 'entity', header: 'Entity', render: (a) => `${a.entity_type}${a.entity_id ? ' #' + a.entity_id : ''}` },
              { key: 'ip_address', header: 'IP' }, { key: 'correlation_id', header: 'Correlation', render: (a) => <span className="mono small">{a.correlation_id}</span> },
            ]} />)}
        {open && <div className="mt"><JsonView value={open} /></div>}
      </Card>
    </>
  );
}
