import { lazy, Suspense, type ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { Spinner } from './components/ui';
import LoginPage from './pages/Login';
import { session } from './services/api';

// Route-level code splitting keeps the initial bundle small.
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Branches = lazy(() => import('./pages/Branches'));
const BranchDetail = lazy(() => import('./pages/BranchDetail'));
const Orders = lazy(() => import('./pages/Orders'));
const DigitalOrders = lazy(() => import('./pages/DigitalOrders'));
const Payments = lazy(() => import('./pages/Payments'));
const Loyalty = lazy(() => import('./pages/Loyalty'));
const PosHub = lazy(() => import('./pages/PosHub'));
const Integrations = lazy(() => import('./pages/Integrations'));
const Webhooks = lazy(() => import('./pages/Webhooks'));
const Automation = lazy(() => import('./pages/Automation'));
const Incidents = lazy(() => import('./pages/Incidents'));
const IncidentDetail = lazy(() => import('./pages/IncidentDetail'));
const Reconciliation = lazy(() => import('./pages/Reconciliation'));
const Reports = lazy(() => import('./pages/Reports'));
const AuditLog = lazy(() => import('./pages/AuditLog'));

function RequireAuth({ children }: { children: ReactNode }) {
  return session.token() ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Dashboard />} />
          <Route path="branches" element={<Branches />} />
          <Route path="branches/:id" element={<BranchDetail />} />
          <Route path="orders" element={<Orders />} />
          <Route path="digital-orders" element={<DigitalOrders />} />
          <Route path="payments" element={<Payments />} />
          <Route path="loyalty" element={<Loyalty />} />
          <Route path="pos" element={<PosHub />} />
          <Route path="integrations" element={<Integrations />} />
          <Route path="webhooks" element={<Webhooks />} />
          <Route path="automation" element={<Automation />} />
          <Route path="incidents" element={<Incidents />} />
          <Route path="incidents/:id" element={<IncidentDetail />} />
          <Route path="reconciliation" element={<Reconciliation />} />
          <Route path="reports" element={<Reports />} />
          <Route path="audit" element={<AuditLog />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
