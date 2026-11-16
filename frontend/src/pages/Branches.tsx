import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DataTable } from '../components/DataTable';
import { Badge, Button, Card, ErrorBox, Field, Modal, PageHeader, Spinner, Toast } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { api, session } from '../services/api';
import type { Branch } from '../services/types';
import { CHANNEL_LABEL } from '../utils/format';

export const PROVINCES = ['Eastern Cape', 'Free State', 'Gauteng', 'KwaZulu-Natal', 'Limpopo', 'Mpumalanga',
  'North West', 'Northern Cape', 'Western Cape'];

const EMPTY = { code: '', name: '', city: '', province: 'KwaZulu-Natal', address: '', phone: '', pos_location_ref: '',
  digital_channels: [] as string[] };

export function validateBranch(f: typeof EMPTY): Record<string, string> {
  const e: Record<string, string> = {};
  if (!/^[A-Z]{3}-[A-Z0-9]{2,6}$/.test(f.code)) e.code = 'Format: 3-letter city code, dash, 2-6 letters/digits (e.g. DBN-UML)';
  if (f.name.trim().length < 2) e.name = 'Name is required';
  if (f.city.trim().length < 2) e.city = 'City is required';
  if (f.phone && !/^0\d{9}$/.test(f.phone.replace(/\s/g, ''))) e.phone = 'South African number, 10 digits starting with 0';
  return e;
}

export default function Branches() {
  const navigate = useNavigate();
  const isAdmin = session.user()?.role === 'admin';
  const [province, setProvince] = useState('');
  const { data, error, loading, reload } = useApi(() => api.get<Branch[]>('/api/v1/branches', { province }), [province]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [touched, setTouched] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const action = useAction();
  const errors = touched ? validateBranch(form) : {};

  const save = async () => {
    setTouched(true);
    if (Object.keys(validateBranch(form)).length) return;
    const created = await action.run(() => api.post<Branch>('/api/v1/branches', { ...form, phone: form.phone.replace(/\s/g, '') }));
    if (created) { setOpen(false); setForm(EMPTY); setTouched(false); setToast(`Branch ${created.code} created`); void reload(); }
  };

  const toggleChannel = (c: string) => setForm((f) => ({ ...f, digital_channels: f.digital_channels.includes(c)
    ? f.digital_channels.filter((x) => x !== c) : [...f.digital_channels, c] }));

  return (
    <>
      <PageHeader title="Restaurant Branches" subtitle="Branch configuration, POS assignment and payment providers"
        actions={<>
          <select className="input" value={province} onChange={(e) => setProvince(e.target.value)} aria-label="Province">
            <option value="">All provinces</option>{PROVINCES.map((p) => <option key={p}>{p}</option>)}
          </select>
          {isAdmin && <Button onClick={() => setOpen(true)}>+ New branch</Button>}
        </>} />
      <Card>
        <ErrorBox error={error} onRetry={reload} />
        {loading ? <Spinner /> : (
          <DataTable rows={data ?? []} rowKey={(b) => b.id} onRowClick={(b) => navigate(`/branches/${b.id}`)}
            columns={[
              { key: 'code', header: 'Code', render: (b) => <span className="mono">{b.code}</span> },
              { key: 'name', header: 'Branch', render: (b) => <><strong>{b.name}</strong><div className="muted small">{b.address}</div></> },
              { key: 'city', header: 'City', render: (b) => `${b.city}, ${b.province}` },
              { key: 'pos', header: 'POS', render: (b) => b.pos_system === 'micros_simphony' ? <>Micros Simphony <span className="muted small mono">{b.pos_location_ref}</span></> : 'None' },
              { key: 'payment_provider', header: 'Payments', render: () => 'Transaction Junction' },
              { key: 'channels', header: 'Digital channels', render: (b) => <div className="chip-list">{b.digital_channels.map((c) => <Badge key={c} value={CHANNEL_LABEL[c]} tone="info" />)}</div> },
              { key: 'is_active', header: 'Status', render: (b) => <Badge value={b.is_active ? 'healthy' : 'disabled'} tone={b.is_active ? 'good' : 'neutral'} /> },
            ]} />
        )}
      </Card>
      <Modal title="Create branch" open={open} onClose={() => setOpen(false)}>
        <ErrorBox error={action.error} />
        <div className="form-grid">
          <Field label="Branch code" error={errors.code} hint="e.g. DBN-GTW">
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="Name" error={errors.name}><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="City" error={errors.city}><input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></Field>
          <Field label="Province">
            <select value={form.province} onChange={(e) => setForm({ ...form, province: e.target.value })}>{PROVINCES.map((p) => <option key={p}>{p}</option>)}</select>
          </Field>
          <Field label="Address"><input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
          <Field label="Phone" error={errors.phone}><input value={form.phone} placeholder="0315550000" onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          <Field label="Simphony location ref" hint="Assigns the branch to the Micros Simphony POS">
            <input value={form.pos_location_ref} onChange={(e) => setForm({ ...form, pos_location_ref: e.target.value })} />
          </Field>
          <Field label="Digital channels">
            <div className="checks">
              {['uber_eats', 'mr_d', 'web'].map((c) => (
                <label key={c}><input type="checkbox" checked={form.digital_channels.includes(c)} onChange={() => toggleChannel(c)} /> {CHANNEL_LABEL[c]}</label>
              ))}
            </div>
          </Field>
        </div>
        <div className="form-actions">
          <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={save} busy={action.busy}>Create branch</Button>
        </div>
      </Modal>
      <Toast message={toast} onDone={() => setToast(null)} />
    </>
  );
}
