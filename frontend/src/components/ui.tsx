import { useEffect, type ReactNode } from 'react';
import { ApiError } from '../services/api';
import { titleCase } from '../utils/format';

export function Card({ title, actions, children, className = '', subtitle }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; subtitle?: ReactNode;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p className="muted small">{subtitle}</p>}
          </div>
          {actions && <div className="row gap-sm">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, hint, tone = 'default', onClick }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: 'default' | 'good' | 'bad' | 'warn'; onClick?: () => void;
}) {
  return (
    <button type="button" className={`kpi tone-${tone} ${onClick ? 'clickable' : ''}`} onClick={onClick}
            disabled={!onClick} aria-label={label}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </button>
  );
}

const TONES: Record<string, string> = {
  healthy: 'good', processed: 'good', captured: 'good', completed: 'good', synced: 'good', resolved: 'good',
  closed: 'neutral', matched: 'good', accepted: 'info', authorised: 'info', preparing: 'info', ready: 'info',
  sent: 'good', delivered: 'good', success: 'good', retried_ok: 'good',
  degraded: 'warn', pending: 'warn', initiated: 'warn', investigating: 'warn', mitigated: 'warn', retrying: 'warn',
  received: 'warn', partially_refunded: 'warn', duplicate: 'neutral', recorded: 'neutral', refunded: 'neutral',
  down: 'bad', failed: 'bad', rejected: 'bad', cancelled: 'neutral', open: 'bad', disabled: 'neutral',
  SEV1: 'bad', SEV2: 'warn', SEV3: 'info', SEV4: 'neutral', simulated: 'neutral',
};

export function Badge({ value, tone }: { value: string | null | undefined; tone?: string }) {
  if (!value) return <span className="muted">—</span>;
  return <span className={`badge badge-${tone ?? TONES[value] ?? 'neutral'}`}>{value.startsWith('SEV') ? value : titleCase(value)}</span>;
}

export function Button({ children, variant = 'primary', busy, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'; busy?: boolean;
}) {
  return (
    <button type="button" {...rest} className={`btn btn-${variant} ${rest.className ?? ''}`} disabled={busy || rest.disabled}>
      {busy && <span className="spinner sm" aria-hidden />}
      {children}
    </button>
  );
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return <div className="loading" role="status"><span className="spinner" aria-hidden /> {label}</div>;
}

export function ErrorBox({ error, onRetry }: { error: Error | null; onRetry?: () => void }) {
  if (!error) return null;
  const api = error instanceof ApiError ? error : null;
  return (
    <div className="alert alert-error" role="alert">
      <div>
        <strong>{api?.code ? titleCase(api.code.toLowerCase()) : 'Something went wrong'}:</strong> {error.message}
        {Array.isArray(api?.details) && (
          <ul className="small">{(api!.details as any[]).map((d, i) => <li key={i}>{d.loc?.slice(1).join('.')}: {d.msg}</li>)}</ul>
        )}
        {api?.correlationId && <div className="small muted">Reference: {api.correlationId}</div>}
      </div>
      {onRetry && <Button variant="secondary" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Empty({ children = 'Nothing to show yet.' }: { children?: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Modal({ title, open, onClose, children, wide }: {
  title: string; open: boolean; onClose: () => void; children: ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}
           onMouseDown={(e) => e.stopPropagation()}>
        <header className="card-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Close">×</button></header>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children, hint, error }: { label: string; children: ReactNode; hint?: string; error?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {error ? <small className="field-error">{error}</small> : hint && <small className="muted">{hint}</small>}
    </label>
  );
}

export function JsonView({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

export function SimulatedTag() {
  return <span className="badge badge-neutral" title="Vendor integration is simulated - no live vendor connection">Simulated</span>;
}

export function Toast({ message, onDone, tone = 'good' }: { message: string | null; onDone: () => void; tone?: string }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onDone, 4000);
    return () => clearTimeout(t);
  }, [message, onDone]);
  if (!message) return null;
  return <div className={`toast toast-${tone}`} role="status">{message}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div><h1>{title}</h1>{subtitle && <p className="muted">{subtitle}</p>}</div>
      {actions && <div className="row gap-sm wrap">{actions}</div>}
    </div>
  );
}
