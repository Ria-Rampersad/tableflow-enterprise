import { useState } from 'react';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, Modal, PageHeader, SimulatedTag, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api } from '../services/api';
import type { LoyaltyAccount, LoyaltyTxn, Paged } from '../services/types';
import { dateTime, num, zar } from '../utils/format';

export default function Loyalty() {
  const [search, setSearch] = useState('');
  const [tier, setTier] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const accounts = useApi(() => api.get<Paged<LoyaltyAccount>>('/api/v1/loyalty/accounts', { search, tier, limit: 50 }), [search, tier]);
  const failed = useApi(() => api.get<Paged<LoyaltyTxn>>('/api/v1/loyalty/transactions', { sync_status: 'failed', limit: 50 }), []);
  const action = useAction();

  const retry = async (id: number) => {
    const r = await action.run(() => api.post<LoyaltyTxn>(`/api/v1/loyalty/transactions/${id}/retry`));
    if (r) { setToast(`Transaction ${id}: ${r.sync_status}`); void failed.reload(); }
  };

  return (
    <>
      <PageHeader title="Loyalty Management" subtitle={<>1 point per R10 spent · points earned on captured payment · synced to loyalty platform <SimulatedTag /></>} />
      <div className="grid grid-3">
        <Card title="Members" className="span-2">
          <div className="filters">
            <Field label="Search"><input placeholder="Name, phone or member no." value={search} onChange={(e) => setSearch(e.target.value)} /></Field>
            <Field label="Tier"><select value={tier} onChange={(e) => setTier(e.target.value)}><option value="">All</option><option>Gold</option><option>Silver</option><option>Bronze</option></select></Field>
          </div>
          <ErrorBox error={accounts.error} />
          {accounts.loading && !accounts.data ? <Spinner /> : (
            <DataTable rows={accounts.data?.items ?? []} rowKey={(a) => a.id} onRowClick={(a) => setSelected(a.id)} columns={[
              { key: 'member_number', header: 'Member', render: (a) => <span className="mono">{a.member_number}</span> },
              { key: 'customer_name', header: 'Customer' }, { key: 'phone', header: 'Phone' },
              { key: 'tier', header: 'Tier', render: (a) => <Badge value={a.tier} tone={a.tier === 'Gold' ? 'warn' : a.tier === 'Silver' ? 'info' : 'neutral'} /> },
              { key: 'points_balance', header: 'Balance', align: 'right', render: (a) => num(a.points_balance) },
              { key: 'lifetime_points', header: 'Lifetime', align: 'right', render: (a) => num(a.lifetime_points) },
            ]} />)}
        </Card>
        <Card title="Failed loyalty syncs" subtitle="Points kept locally; retry pushes them to the platform">
          <ErrorBox error={action.error} />
          <DataTable dense rows={failed.data?.items ?? []} rowKey={(t) => t.id} empty="All loyalty transactions are synced" columns={[
            { key: 'id', header: '#' }, { key: 'points', header: 'Pts', align: 'right' },
            { key: 'error', header: 'Error', render: (t) => <span className="small">{t.error}</span> },
            { key: 'act', header: '', render: (t) => <Button variant="secondary" busy={action.busy} onClick={() => retry(t.id)}>Retry</Button> },
          ]} />
        </Card>
      </div>
      <Modal title="Loyalty account" open={selected !== null} onClose={() => setSelected(null)} wide>
        {selected !== null && <AccountDetail id={selected} onRedeemed={(m) => { setToast(m); void accounts.reload(); }} />}
      </Modal>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}

function AccountDetail({ id, onRedeemed }: { id: number; onRedeemed: (m: string) => void }) {
  const d = useApi(() => api.get<{ account: LoyaltyAccount; transactions: LoyaltyTxn[] }>(`/api/v1/loyalty/accounts/${id}`), [id]);
  const [points, setPoints] = useState(50);
  const action = useAction();
  if (d.loading && !d.data) return <Spinner />;
  if (!d.data) return <ErrorBox error={d.error} />;
  const a = d.data.account;
  const redeem = async () => {
    if (points <= 0 || points > a.points_balance) { action.setError(new Error(`Choose between 1 and ${a.points_balance} points`)); return; }
    if (await action.run(() => api.post(`/api/v1/loyalty/accounts/${id}/redeem`, { points }))) {
      onRedeemed(`Redeemed ${points} points (${zar(points * 0.1)} value)`);
      void d.reload();
    }
  };
  return (
    <div className="stack">
      <ErrorBox error={action.error} />
      <div className="grid grid-3">
        <div><div className="muted small">Member</div><strong>{a.customer_name}</strong><div className="mono small">{a.member_number}</div></div>
        <div><div className="muted small">Balance</div><strong>{num(a.points_balance)} pts</strong><div className="small">≈ {zar(a.points_balance * 0.1)}</div></div>
        <div><div className="muted small">Tier</div><Badge value={a.tier} /></div>
      </div>
      <div className="row gap-sm">
        <input className="input" type="number" min={1} value={points} onChange={(e) => setPoints(Number(e.target.value))} aria-label="Points to redeem" />
        <Button busy={action.busy} onClick={redeem}>Redeem points</Button>
      </div>
      <DataTable dense rows={d.data.transactions} rowKey={(t) => t.id} columns={[
        { key: 'created_at', header: 'When', render: (t) => dateTime(t.created_at) },
        { key: 'type', header: 'Type', render: (t) => <Badge value={t.type} tone={t.type === 'earn' ? 'good' : 'info'} /> },
        { key: 'points', header: 'Points', align: 'right', render: (t) => (t.type === 'redeem' ? '−' : '+') + t.points },
        { key: 'order_id', header: 'Order #' },
        { key: 'sync_status', header: 'Platform sync', render: (t) => <Badge value={t.sync_status} /> },
        { key: 'external_ref', header: 'Platform ref', render: (t) => <span className="mono small">{t.external_ref ?? t.error ?? ''}</span> },
      ]} />
    </div>
  );
}
