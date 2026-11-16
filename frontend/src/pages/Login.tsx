import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, ErrorBox, Field } from '../components/ui';
import { login } from '../services/api';

const DEMO = [
  ['admin@tableflow.local', 'Admin'],
  ['finance@tableflow.local', 'Finance'],
  ['ops@tableflow.local', 'Operations'],
  ['manager.umhlanga@tableflow.local', 'Branch manager'],
  ['engineer@tableflow.local', 'Integration engineer'],
];

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('admin@tableflow.local');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);

  const emailError = touched && !/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(email) ? 'Enter a valid email address' : undefined;
  const pwError = touched && password.length < 8 ? 'Password must be at least 8 characters' : undefined;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(email) || password.length < 8) return;
    setBusy(true);
    setError(null);
    try {
      await login(email.trim().toLowerCase(), password);
      navigate('/');
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-hero">
        <div className="row gap-sm"><img src="/favicon.svg" width={34} height={34} alt="" /><strong>TableFlow Enterprise</strong></div>
        <div>
          <h1>One control room for orders, payments, POS and loyalty across every branch.</h1>
          <ul>
            <li>Micros Simphony, Transaction Junction, Uber Eats and Mr D integrations</li>
            <li>Automated reconciliation, incident management and n8n workflows</li>
            <li>Real-time integration health, webhooks and audit trail</li>
          </ul>
        </div>
        <p className="small">Portfolio project · all vendor integrations are simulated · fictional data</p>
      </div>
      <div className="login-form">
        <form className="card login-card" onSubmit={submit} noValidate>
          <h2>Sign in</h2>
          <p className="muted small">OAuth 2.0 password flow → JWT bearer token</p>
          <ErrorBox error={error} />
          <div className="stack">
            <Field label="Email" error={emailError}>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
            </Field>
            <Field label="Password" error={pwError}>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                     autoComplete="current-password" />
            </Field>
            <Button type="submit" busy={busy} className="w-full">Sign in</Button>
          </div>
          <div className="demo-users">
            <span className="muted small">Demo accounts (password <code>TableFlow!2026</code>):</span>
            {DEMO.map(([e, r]) => (
              <button type="button" key={e} onClick={() => { setEmail(e); setPassword('TableFlow!2026'); }}>
                <strong>{r}</strong> · {e}
              </button>
            ))}
          </div>
        </form>
      </div>
    </div>
  );
}
