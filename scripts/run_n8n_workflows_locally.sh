#!/usr/bin/env bash
# Executes all 8 n8n workflow files against a running TableFlow API using the local runner
# (automation/local-runner). Requires: node >= 18, API on $TABLEFLOW_API_URL.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${TABLEFLOW_API_URL:=http://localhost:8000}" "${TABLEFLOW_CLIENT_ID:=n8n-automation}"
: "${TABLEFLOW_CLIENT_SECRET:=dev-n8n-secret-change-me}" "${ALERT_TOKEN:=dev-alert-sink-token}"
: "${ALERT_WEBHOOK_URL:=$TABLEFLOW_API_URL/api/v1/alerts/sink}"
export TABLEFLOW_API_URL TABLEFLOW_CLIENT_ID TABLEFLOW_CLIENT_SECRET ALERT_TOKEN ALERT_WEBHOOK_URL
R=automation/local-runner/n8n-local-runner.mjs; D=automation/n8n
node $R $D/01_failed_payment_notifications.json --payload '{"event_type":"payment.failed","payment_id":1,"order_number":"TF-DEMO-1","branch":"JHB-SDN","amount":"649.90","reason":"51 Insufficient funds"}'
node $R $D/02_failed_pos_integration.json --payload '{"event_type":"pos.order_forward_failed","order_number":"TF-DEMO-2","branch":"PMB-LBT","error":"Simphony unavailable (HTTP 503)"}'
node $R $D/03_new_order_processing.json --payload '{"event_type":"order.received","order_number":"TF-DEMO-3","branch":"DBN-UML","channel":"uber_eats","total":"1259.40"}'
node $R $D/04_loyalty_point_updates.json --payload '{"event_type":"loyalty.sync_failed","member_number":"SF100001","points":12}'
node $R $D/05_daily_financial_reconciliation.json
node $R $D/06_low_stock_notifications.json
node $R $D/07_incident_escalation.json --payload '{"event_type":"incident.created","id":1,"reference":"INC-00001","title":"Gateway down","severity":"SEV1","category":"payment"}'
node $R $D/08_daily_management_reporting.json
echo "all 8 workflows executed"
