import { useState } from 'react';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, Kpi, PageHeader, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { Branch, Paged, ReconRun } from '../services/types';
import { dateTime, isoDay, num, titleCase, zar } from '../utils/format';

const ISSUE_HELP: Record<string, string> = {
  missing_payment: 'Order fulfilled but no payment recorded',
  failed_payment: 'Only failed payment attempts exist',
  duplicate_payment: 'Customer charged more than once',
  amount_mismatch: 'Captured amount differs from order total',
  missing_pos_record: 'Order sent to POS but no closed Simphony check',
  pos_amount_mismatch: 'Simphony check total differs from order',
  missing_settlement: 'Captured payment not on acquirer settlement',
  settlement_mismatch: 'Settled amount differs from captured amount',
  unknown_settlement: 'Settlement line with no TableFlow payment',
};

export default function Reconciliation() {
  const [date, setDate] = useState(isoDay(-1));
  const [branchId, setBranchId] = useState('');
  const [runId, setRunId] = useState<number | null>(null);
  const [filter, setFilter] = useState('');
  const [toast, setToast] = useState<string | null>(null);
  const branches = useApi(() => api.get<Branch[]>('/api/v1/branches'), []);
  const runs = useApi(() => api.get<Paged<ReconRun>>('/api/v1/reconciliation/runs', { limit: 15 }), []);
  const run = useApi(() => runId ? api.get<ReconRun>(`/api/v1/reconciliation/runs/${runId}`) : Promise.resolve(null), [runId]);
  const action = useAction();
  const r = run.data;

  const start = async () => {
    const res = await action.run(() => api.post<ReconRun>('/api/v1/reconciliation/runs', { business_date: date, branch_id: branchId ? Number(branchId) : null }));
    if (res) { setRunId(res.id); run.setData(res); void runs.reload(); }
  };
  const resolve = async (id: number) => { if (await action.run(() => api.patch(`/api/v1/reconciliation/records/${id}/resolve`))) void run.reload(); };
  const upload = async (file: File | undefined) => {
    if (!file) return;
    const res = await action.run(() => api.upload<any>('/api/v1/reconciliation/settlements/import', file));
    if (res) setToast(`Imported ${res.inserted} settlement lines (${res.skipped_duplicates} duplicates skipped, ${res.errors.length} errors)`);
  };
  const branchName = (id: number | null) => branches.data?.find((b) => b.id === id)?.code ?? '—';
  const records = (r?.records ?? []).filter((x) => !filter || x.issue_type === filter);

  return (
    <>
      <PageHeader title="Financial Reconciliation" subtitle="Matches POS checks, digital orders, payments and acquirer settlements for a business day" />
      <ErrorBox error={action.error} />
      <div className="grid grid-3">
        <Card title="Run reconciliation" className="span-2">
          <div className="filters">
            <Field label="Business date"><input type="date" value={date} max={isoDay(0)} onChange={(e) => setDate(e.target.value)} /></Field>
            <Field label="Branch"><select value={branchId} onChange={(e) => setBranchId(e.target.value)}><option value="">All branches</option>
              {branches.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>
            <Button busy={action.busy} onClick={start}>Reconcile</Button>
            <label className="btn btn-secondary">Import settlement CSV<input type="file" accept=".csv" hidden onChange={(e) => upload(e.target.files?.[0])} /></label>
          </div>
          <p className="muted small">Matching keys: order → payments (order_id), order → Simphony check (pos_check_ref), payment → settlement (gateway reference). An order counts as <em>matched</em> only when every check passes.</p>
        </Card>
        <Card title="Recent runs">
          <DataTable dense rows={runs.data?.items ?? []} rowKey={(x) => x.id} onRowClick={(x) => setRunId(x.id)} columns={[
            { key: 'business_date', header: 'Date' }, { key: 'branch_id', header: 'Branch', render: (x) => x.branch_id ? branchName(x.branch_id) : 'All' },
            { key: 'discrepancies', header: 'Issues', align: 'right' }, { key: 'discrepancy_value', header: 'Value', align: 'right', render: (x) => zar(x.discrepancy_value) }]} />
        </Card>
      </div>
      {run.loading && runId ? <Spinner /> : r && (
        <>
          <div className="grid grid-kpi mt">
            <Kpi label="Orders reconciled" value={num(r.total_orders)} hint={`${r.business_date} · run #${r.id}`} />
            <Kpi label="Matched" value={num(r.matched)} tone="good" hint={r.total_orders ? `${((r.matched / r.total_orders) * 100).toFixed(1)}%` : ''} />
            <Kpi label="Discrepancies" value={num(r.discrepancies)} tone={r.discrepancies ? 'bad' : 'good'} />
            <Kpi label="Value at risk" value={zar(r.discrepancy_value)} tone={Number(r.discrepancy_value) > 500 ? 'bad' : 'warn'} hint="> R500 raises an incident" />
          </div>
          <Card className="mt" title="Discrepancies" subtitle={`Run by ${r.run_by} · ${dateTime(r.completed_at)}`}
                actions={<Button variant="secondary" onClick={() => api.download(`/api/v1/reconciliation/runs/${r.id}/export`, undefined, `reconciliation_${r.business_date}.csv`)}>Export CSV</Button>}>
            <div className="chip-list" style={{ marginBottom: 12 }}>
              <button className={`btn ${filter ? 'btn-secondary' : 'btn-primary'}`} onClick={() => setFilter('')}>All</button>
              {Object.entries(r.summary ?? {}).map(([k, v]) => (
                <button key={k} title={ISSUE_HELP[k]} className={`btn ${filter === k ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setFilter(k)}>{titleCase(k)} · {v}</button>))}
            </div>
            <DataTable dense rows={records} rowKey={(x) => x.id} empty="No discrepancies — books balance" columns={[
              { key: 'issue_type', header: 'Issue', render: (x) => <span title={ISSUE_HELP[x.issue_type]}><Badge value={x.issue_type} tone="bad" /></span> },
              { key: 'branch_id', header: 'Branch', render: (x) => <span className="mono">{branchName(x.branch_id)}</span> },
              { key: 'order_id', header: 'Order #' }, { key: 'payment_id', header: 'Payment #' },
              { key: 'expected_amount', header: 'Expected', align: 'right', render: (x) => zar(x.expected_amount) },
              { key: 'actual_amount', header: 'Actual', align: 'right', render: (x) => zar(x.actual_amount) },
              { key: 'difference', header: 'Diff', align: 'right', render: (x) => zar(x.difference) },
              { key: 'details', header: 'Details', render: (x) => <span className="small">{x.details}</span> },
              { key: 'resolved', header: '', render: (x) => x.resolved ? <Badge value="resolved" /> : <Button variant="ghost" onClick={() => resolve(x.id)}>Mark resolved</Button> },
            ]} />
          </Card>
        </>)}
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}
