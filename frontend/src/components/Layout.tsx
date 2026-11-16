import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { session } from '../services/api';
import { titleCase } from '../utils/format';

const NAV: { group: string; items: { to: string; label: string; icon: string; roles?: string[] }[] }[] = [
  { group: 'Overview', items: [
    { to: '/', label: 'Executive Dashboard', icon: '◧' },
    { to: '/reports', label: 'Reports & Analytics', icon: '▤' },
  ] },
  { group: 'Operations', items: [
    { to: '/branches', label: 'Branches', icon: '⌂' },
    { to: '/orders', label: 'Orders', icon: '☰' },
    { to: '/digital-orders', label: 'Digital Ordering', icon: '⇄' },
    { to: '/payments', label: 'Payments', icon: '₨' },
    { to: '/loyalty', label: 'Loyalty', icon: '★' },
  ] },
  { group: 'Integrations', items: [
    { to: '/pos', label: 'POS Integration Hub', icon: '▣' },
    { to: '/integrations', label: 'Integration Monitoring', icon: '◉' },
    { to: '/webhooks', label: 'Webhooks', icon: '↯' },
  ] },
  { group: 'Control', items: [
    { to: '/automation', label: 'Automation', icon: '⚙' },
    { to: '/incidents', label: 'Incidents', icon: '⚠' },
    { to: '/reconciliation', label: 'Reconciliation', icon: '⚖' },
    { to: '/audit', label: 'Audit Trail', icon: '⎙', roles: ['admin', 'finance'] },
  ] },
];

export default function Layout() {
  const navigate = useNavigate();
  const user = session.user();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const out = () => navigate('/login');
    window.addEventListener('tableflow:logout', out);
    return () => window.removeEventListener('tableflow:logout', out);
  }, [navigate]);

  const logout = () => { session.clear(); navigate('/login'); };

  return (
    <div className={`shell ${open ? 'nav-open' : ''}`}>
      <aside className="sidebar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={30} height={30} />
          <div><strong>TableFlow</strong><span>Enterprise</span></div>
        </div>
        <nav onClick={() => setOpen(false)}>
          {NAV.map((g) => (
            <div key={g.group} className="nav-group">
              <div className="nav-title">{g.group}</div>
              {g.items.filter((i) => !i.roles || i.roles.includes(user?.role ?? '') || user?.role === 'admin').map((i) => (
                <NavLink key={i.to} to={i.to} end={i.to === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                  <span className="nav-icon" aria-hidden>{i.icon}</span>{i.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot small">Shisa Flame Chicken (fictional)<br />Vendor integrations simulated</div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setOpen(!open)} aria-label="Toggle navigation">☰</button>
          <div className="env-pill">Demo environment · ZAR · SAST</div>
          <div className="user">
            <div className="avatar" aria-hidden>{user?.full_name?.[0] ?? '?'}</div>
            <div className="user-meta">
              <strong>{user?.full_name}</strong>
              <span>{titleCase(user?.role ?? '')}</span>
            </div>
            <button className="btn btn-ghost" onClick={logout}>Sign out</button>
          </div>
        </header>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
