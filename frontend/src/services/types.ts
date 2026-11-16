// Response shapes returned by the FastAPI backend (see backend/app/schemas).

export interface Paged<T> { total: number; items: T[]; }

export interface Branch {
  id: number; code: string; name: string; city: string; province: string; address: string; phone: string;
  pos_system: string; pos_location_ref: string; payment_provider: string; digital_channels: string[];
  is_active: boolean; opened_on: string | null;
}

export interface OrderItem { sku: string; name: string; quantity: number; unit_price: string; line_total: string; }

export interface Order {
  id: number; order_number: string; branch_id: number; branch_name: string; channel: string;
  external_ref: string | null; status: string; subtotal: string; vat: string; total: string;
  pos_check_ref: string | null; customer_id: number | null; created_at: string; items: OrderItem[];
  payment_status: string | null;
}

export interface Payment {
  id: number; order_id: number; provider: string; provider_reference: string | null; amount: string;
  currency: string; method: string; status: string; failure_reason: string | null; refunded_amount: string;
  created_at: string;
}

export interface Integration {
  id: number; name: string; display_name: string; kind: string; provider: string; mode: string; status: string;
  last_success_at: string | null; last_failure_at: string | null; consecutive_failures: number;
  total_requests: number; total_failures: number; avg_response_ms: number; last_error: string | null;
  config: { simulate_outage?: boolean; failure_rate?: number; latency_ms?: number };
}

export interface IntegrationLog {
  id: number; integration_id: number; operation: string; status: string; http_status: number | null;
  response_ms: number; attempt: number; correlation_id: string; entity_type: string | null; entity_id: number | null;
  request_payload: unknown; response_payload: unknown; error_message: string | null; created_at: string;
}

export interface WebhookEvent {
  id: number; source: string; event_id: string; event_type: string; payload: unknown; signature_valid: boolean;
  status: string; attempts: number; error: string | null; received_at: string; processed_at: string | null;
}

export interface Incident {
  id: number; reference: string; title: string; description: string; severity: string; status: string;
  category: string; source: string; branch_id: number | null; integration_id: number | null;
  assigned_to_id: number | null; escalation_level: number; root_cause: string | null;
  resolution_notes: string | null; opened_at: string; resolved_at: string | null;
  events?: { id: number; event_type: string; message: string; actor: string; created_at: string }[];
}

export interface LoyaltyAccount {
  id: number; member_number: string; customer_name: string; phone: string; points_balance: number;
  lifetime_points: number; tier: string;
}

export interface LoyaltyTxn {
  id: number; account_id: number; order_id: number | null; type: string; points: number; sync_status: string;
  external_ref: string | null; error: string | null; attempts: number; created_at: string;
}

export interface ReconRecord {
  id: number; branch_id: number | null; order_id: number | null; payment_id: number | null; issue_type: string;
  expected_amount: string | null; actual_amount: string | null; difference: string | null; details: string;
  resolved: boolean;
}

export interface ReconRun {
  id: number; business_date: string; branch_id: number | null; status: string; total_orders: number;
  matched: number; discrepancies: number; discrepancy_value: string; run_by: string; started_at: string;
  completed_at: string | null; summary?: Record<string, number>; records?: ReconRecord[];
}

export interface DashboardSummary {
  period: { start: string; end: string; branch_id: number | null };
  branches: number; total_orders: number; total_sales_zar: number; average_order_value_zar: number;
  payments: { successful: number; failed: number; pending: number; success_rate: number };
  integration_health: { healthy: number; total: number;
    items: { id: number; name: string; status: string; kind: string; avg_response_ms: number }[] };
  api_request_volume: { integration_calls: number; api_requests_since_start: number };
  failed_webhook_events: number;
  system: { uptime_seconds: number; latency_ms: { p50: number; p95: number; p99: number }; error_rate: number };
}

export interface BranchPerf {
  branch_id: number; code: string; name: string; city: string; province: string; orders: number; revenue: number;
  avg_ticket: number; failed_orders: number; cancelled_orders: number; failed_payments: number;
}

export interface Notification {
  id: number; workflow: string; event_type: string; status: string; payload: Record<string, unknown>;
  target_url: string; error: string | null; created_at: string;
}
