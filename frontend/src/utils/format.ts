const zarFmt = new Intl.NumberFormat('en-ZA', { style: 'currency', currency: 'ZAR', minimumFractionDigits: 2 });
const intFmt = new Intl.NumberFormat('en-ZA');

/** R 1 234,50 style South African Rand formatting. */
export const zar = (v: number | string | null | undefined): string =>
  v === null || v === undefined || v === '' ? '—' : zarFmt.format(Number(v));

/** Compact Rand for chart axes: R12k, R1.2m */
export const zarCompact = (v: number): string =>
  v >= 1_000_000 ? `R${(v / 1_000_000).toFixed(1)}m` : v >= 1000 ? `R${Math.round(v / 1000)}k` : `R${Math.round(v)}`;

export const num = (v: number | null | undefined): string => (v === null || v === undefined ? '—' : intFmt.format(v));

export const pct = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined ? '—' : `${v.toFixed(digits)}%`;

export const dateTime = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`);
  return d.toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit' });
};

export const shortDate = (iso: string): string =>
  new Date(`${iso}T12:00:00`).toLocaleDateString('en-ZA', { day: '2-digit', month: 'short' });

export const duration = (seconds: number): string => {
  const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m ${Math.floor(seconds % 60)}s`;
};

export const titleCase = (s: string): string => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/** YYYY-MM-DD for <input type=date>, in SAST. */
export const isoDay = (offsetDays = 0): string => {
  const d = new Date(Date.now() + 2 * 3600_000 + offsetDays * 86400_000);
  return d.toISOString().slice(0, 10);
};

export const CHANNEL_LABEL: Record<string, string> = {
  in_store: 'In-store', web: 'Web', uber_eats: 'Uber Eats', mr_d: 'Mr D',
};
