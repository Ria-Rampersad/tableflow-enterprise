"""Generate the 8 importable n8n workflow JSON files in automation/n8n/.

Workflows are generated from Python (rather than hand-exported) so that every
workflow uses the same conventions:
  * API base URL, client id/secret and alert URL come from n8n environment variables
    (TABLEFLOW_API_URL, TABLEFLOW_CLIENT_ID, TABLEFLOW_CLIENT_SECRET, ALERT_WEBHOOK_URL, ALERT_TOKEN)
  * Authentication to TableFlow uses the OAuth 2.0 client-credentials grant
  * Alerts are Slack-compatible JSON ({"text": ..., "channel": ...}) so ALERT_WEBHOOK_URL can be a real
    Slack/Teams incoming webhook or TableFlow's local alert sink.
Node types/versions: webhook v2, scheduleTrigger v1.2, httpRequest v4.2, if v2, code v2, wait v1.1, noOp v1.
"""
import json
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "automation" / "n8n"
API = "{{ $env.TABLEFLOW_API_URL }}"
TOKEN_EXPR = "=Bearer {{ $('Get API token').item.json.access_token }}"


def nid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


class WF:
    def __init__(self, name, tags):
        self.name, self.tags = name, tags
        self.nodes, self.conn, self.x = [], {}, 0

    def add(self, name, type_, params, version, pos=None, **extra):
        self.x += 240
        node = {"parameters": params, "id": nid(self.name + name), "name": name, "type": type_,
                "typeVersion": version, "position": pos or [self.x, 300], **extra}
        self.nodes.append(node)
        return name

    def link(self, src, dst, output=0):
        outs = self.conn.setdefault(src, {"main": []})["main"]
        while len(outs) <= output:
            outs.append([])
        outs[output].append({"node": dst, "type": "main", "index": 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def to_json(self):
        return {"name": self.name, "nodes": self.nodes, "connections": self.conn, "active": False,
                "settings": {"executionOrder": "v1", "timezone": "Africa/Johannesburg"},
                "tags": [{"name": t} for t in self.tags], "meta": {"templateCredsSetupCompleted": True},
                "pinData": {}}


# ------------------------------------------------------------------ node helpers
def webhook(wf, path):
    return wf.add("Webhook", "n8n-nodes-base.webhook",
                  {"httpMethod": "POST", "path": path, "responseMode": "onReceived", "options": {}}, 2,
                  webhookId=nid(path))


def schedule(wf, cron, label):
    return wf.add(label, "n8n-nodes-base.scheduleTrigger",
                  {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}}, 1.2)


def token(wf, pos=None):
    return wf.add("Get API token", "n8n-nodes-base.httpRequest", {
        "method": "POST", "url": f"={API}/api/v1/auth/token",
        "sendBody": True, "contentType": "form-urlencoded",
        "bodyParameters": {"parameters": [
            {"name": "grant_type", "value": "client_credentials"},
            {"name": "client_id", "value": "={{ $env.TABLEFLOW_CLIENT_ID }}"},
            {"name": "client_secret", "value": "={{ $env.TABLEFLOW_CLIENT_SECRET }}"}]},
        "options": {}}, 4.2, pos)


def api(wf, name, method, path, body_expr=None, pos=None, query=None):
    params = {"method": method, "url": f"={API}{path}", "sendHeaders": True,
              "headerParameters": {"parameters": [{"name": "Authorization", "value": TOKEN_EXPR}]}, "options": {}}
    if query:
        params["sendQuery"] = True
        params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
    if body_expr:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body_expr})
    return wf.add(name, "n8n-nodes-base.httpRequest", params, 4.2, pos)


def alert(wf, name, channel, text_expr, pos=None):
    return wf.add(name, "n8n-nodes-base.httpRequest", {
        "method": "POST", "url": "={{ $env.ALERT_WEBHOOK_URL }}", "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "X-Alert-Token", "value": "={{ $env.ALERT_TOKEN }}"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ channel: '" + channel + "', text: " + text_expr + " }) }}",
        "options": {}}, 4.2, pos)


def if_node(wf, name, left, op, right, type_="number", pos=None):
    cond = {"id": nid(wf.name + name + "c"), "leftValue": left, "operator": {"type": type_, "operation": op}}
    if right is not None:
        cond["rightValue"] = right
    return wf.add(name, "n8n-nodes-base.if", {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                       "conditions": [cond], "combinator": "and"}, "options": {}}, 2, pos)


def code(wf, name, js, pos=None):
    return wf.add(name, "n8n-nodes-base.code", {"jsCode": js}, 2, pos)


def noop(wf, name, pos=None):
    return wf.add(name, "n8n-nodes-base.noOp", {}, 1, pos)


workflows = []

# 1 ---------------------------------------------------------------- failed payment
w = WF("TableFlow 01 - Failed payment notification", ["tableflow", "payments"])
a = webhook(w, "tableflow-failed-payment")
b = code(w, "Format alert", """const p = $input.first().json.body ?? $input.first().json;
const amount = Number(p.amount || 0);
return [{ json: { ...p, amount, high_value: amount >= 500,
  text: `:x: Payment failed at ${p.branch ?? 'unknown branch'} - R${amount.toFixed(2)} (order ${p.order_number ?? '?'}): ${p.reason}` } }];""")
c = if_node(w, "High value (>= R500)?", "={{ $json.amount }}", "gte", 500)
d = alert(w, "Alert finance channel", "#finance-alerts", "$('Format alert').item.json.text", [960, 160])
e = token(w, [960, 440])
f = api(w, "Raise incident", "POST", "/api/v1/incidents",
        "={{ JSON.stringify({ title: 'High-value payment failure ' + $('Format alert').item.json.order_number, "
        "severity: 'SEV3', category: 'payment', description: $('Format alert').item.json.text }) }}", [1200, 440])
g = alert(w, "Alert ops channel", "#ops-alerts", "$('Format alert').item.json.text", [1200, 600])
w.chain(a, b, c)
w.link(c, d, 0)
w.link(c, e, 0)
w.link(c, g, 1)
w.link(e, f)
workflows.append(("01_failed_payment_notifications", w))

# 2 ---------------------------------------------------------------- POS failure
w = WF("TableFlow 02 - Failed POS integration", ["tableflow", "pos"])
a = webhook(w, "tableflow-pos-failure")
b = token(w)
c = api(w, "Get POS status", "GET", "/api/v1/pos/status")
d = code(w, "Assess impact", """const evt = $('Webhook').first().json.body ?? $('Webhook').first().json;
const failed = $input.first().json.failed_orders || [];
return [{ json: { failed_count: failed.length, branch: evt.branch, error: evt.error,
  text: `:warning: Simphony POS failure (${evt.event_type}) at ${evt.branch}: ${evt.error}. ${failed.length} order(s) awaiting retry.` } }];""")
e = if_node(w, "3+ orders stuck?", "={{ $json.failed_count }}", "gte", 3)
f = api(w, "Raise POS incident", "POST", "/api/v1/incidents",
        "={{ JSON.stringify({ title: 'POS forwarding failures at ' + $json.branch, severity: 'SEV2', "
        "category: 'pos', description: $json.text }) }}", [1440, 160])
g = alert(w, "Alert ops channel", "#ops-alerts", "$('Assess impact').item.json.text", [1440, 440])
w.chain(a, b, c, d, e)
w.link(e, f, 0)
w.link(e, g, 0)
w.link(e, g, 1)
workflows.append(("02_failed_pos_integration", w))

# 3 ---------------------------------------------------------------- new order
w = WF("TableFlow 03 - New order processing", ["tableflow", "orders"])
a = webhook(w, "tableflow-new-order")
b = code(w, "Classify order", """const o = $input.first().json.body ?? $input.first().json;
const total = Number(o.total || 0);
const digital = ['uber_eats', 'mr_d'].includes(o.channel);
return [{ json: { ...o, total, large_digital: digital && total >= 1000,
  text: `:package: Large ${o.channel} order ${o.order_number} at ${o.branch}: R${total.toFixed(2)} - check kitchen capacity` } }];""")
c = if_node(w, "Large digital order?", "={{ $json.large_digital }}", "true", None, "boolean")
d = alert(w, "Alert branch channel", "#branch-ops", "$json.text", [960, 160])
e = noop(w, "Normal order - no action", [960, 440])
w.chain(a, b, c)
w.link(c, d, 0)
w.link(c, e, 1)
workflows.append(("03_new_order_processing", w))

# 4 ---------------------------------------------------------------- loyalty
w = WF("TableFlow 04 - Loyalty point updates", ["tableflow", "loyalty"])
a = webhook(w, "tableflow-loyalty-update")
b = if_node(w, "Sync failed?", "={{ ($json.body ?? $json).event_type }}", "equals", "loyalty.sync_failed", "string")
c = token(w, [720, 160])
d = api(w, "List failed syncs", "GET", "/api/v1/loyalty/transactions", query={"sync_status": "failed", "limit": "20"},
        pos=[960, 160])
e = code(w, "Split transactions", "return ($input.first().json.items || []).map(t => ({ json: { id: t.id } }));",
        [1200, 160])
f = api(w, "Retry sync", "POST", "/api/v1/loyalty/transactions/{{ $json.id }}/retry", pos=[1440, 160])
g = code(w, "Summarise", """const all = $input.all();
const ok = all.filter(i => i.json.sync_status === 'synced').length;
return [{ json: { text: `:repeat: Loyalty retry: ${ok}/${all.length} transactions re-synced` } }];""", [1680, 160])
h = alert(w, "Alert CRM channel", "#crm", "$json.text", [1920, 160])
i = noop(w, "Points earned - no action", [720, 440])
w.chain(a, b)
w.link(b, c, 0)
w.link(b, i, 1)
w.chain(c, d, e, f, g, h)
w.nodes[-4]["onError"] = "continueRegularOutput"  # one failed retry must not stop the others
workflows.append(("04_loyalty_point_updates", w))

# 5 ---------------------------------------------------------------- daily reconciliation
w = WF("TableFlow 05 - Daily financial reconciliation", ["tableflow", "finance"])
a = schedule(w, "0 6 * * *", "Every day 06:00 SAST")
b = token(w)
c = api(w, "Run reconciliation", "POST", "/api/v1/automation/daily-reconciliation")
d = if_node(w, "Discrepancies found?", "={{ $json.discrepancies }}", "gt", 0)
e = api(w, "Get run detail", "GET", "/api/v1/reconciliation/runs/{{ $json.run_id }}", pos=[1200, 160])
f = code(w, "Build finance summary", """const r = $input.first().json;
const lines = Object.entries(r.summary || {}).filter(([k]) => k !== 'matched').map(([k, v]) => `- ${k}: ${v}`);
return [{ json: { text: `:bar_chart: Reconciliation ${r.business_date}: ${r.matched}/${r.total_orders} orders matched, ` +
  `${r.discrepancies} discrepancies (R${r.discrepancy_value}).\\n${lines.join('\\n')}\\nRun #${r.id}` } }];""", [1440, 160])
g = alert(w, "Alert finance channel", "#finance", "$json.text", [1680, 160])
h = alert(w, "Post clean result", "#finance", "'Reconciliation ' + $json.business_date + ': all orders matched'",
          [1200, 440])
w.chain(a, b, c, d)
w.link(d, e, 0)
w.link(d, h, 1)
w.chain(e, f, g)
workflows.append(("05_daily_financial_reconciliation", w))

# 6 ---------------------------------------------------------------- low stock
w = WF("TableFlow 06 - Low-stock notifications", ["tableflow", "operations"])
a = schedule(w, "0 9-20/3 * * *", "Every 3h during trading")
b = token(w)
c = api(w, "Get low stock", "GET", "/api/v1/automation/low-stock")
d = if_node(w, "Anything low?", "={{ $json.count }}", "gt", 0)
e = code(w, "Group by branch", """const items = $input.first().json.items;
const byBranch = {};
for (const i of items) (byBranch[i.branch] ??= []).push(`${i.item}: ${i.on_hand} ${i.unit} (re-order at ${i.reorder_level})`);
return Object.entries(byBranch).map(([branch, lines]) => ({ json: { branch,
  text: `:shopping_trolley: Low stock at ${branch}:\\n- ` + lines.join('\\n- ') } }));""", [1200, 160])
f = alert(w, "Alert branch", "#procurement", "$json.text", [1440, 160])
g = noop(w, "Stock OK", [1200, 440])
w.chain(a, b, c, d)
w.link(d, e, 0)
w.link(d, g, 1)
w.chain(e, f)
workflows.append(("06_low_stock_notifications", w))

# 7 ---------------------------------------------------------------- incident escalation
w = WF("TableFlow 07 - Incident escalation", ["tableflow", "incidents"])
a = webhook(w, "tableflow-incident-escalation")
b = code(w, "Normalise", """const e = $input.first().json.body ?? $input.first().json;
return [{ json: { ...e, text: `:rotating_light: ${e.severity} ${e.reference}: ${e.title}` +
  (e.escalated_to ? ` - escalated to ${e.escalated_to}` : '') } }];""")
c = if_node(w, "SEV1?", "={{ $json.severity }}", "equals", "SEV1", "string")
d = alert(w, "Page on-call engineer", "#on-call", "'PAGE: ' + $json.text", [960, 160])
e = alert(w, "Post to incident channel", "#incidents", "$('Normalise').item.json.text", [960, 440])
f = if_node(w, "New incident (not already escalated)?", "={{ $('Normalise').item.json.event_type }}", "equals",
            "incident.created", "string", [1200, 440])
g = w.add("Wait 30 minutes", "n8n-nodes-base.wait", {"amount": 30, "unit": "minutes"}, 1.1, [1440, 440],
          webhookId=nid("wait-30"))
h = token(w, [1680, 440])
i = api(w, "Get incident", "GET", "/api/v1/incidents/{{ $('Normalise').item.json.id }}", pos=[1920, 440])
j = if_node(w, "Still open?", "={{ $json.status }}", "equals", "open", "string", [2160, 440])
k = api(w, "Auto-escalate", "POST", "/api/v1/incidents/{{ $json.id }}/escalate",
        "={{ JSON.stringify({ reason: 'Auto-escalated by n8n: no acknowledgement within 30 minutes' }) }}",
        pos=[2400, 360])
w.chain(a, b, c)
w.link(c, d, 0)
w.link(c, e, 0)
w.link(c, e, 1)
w.chain(e, f)
w.link(f, g, 0)
w.chain(g, h, i, j)
w.link(j, k, 0)
workflows.append(("07_incident_escalation", w))

# 8 ---------------------------------------------------------------- daily management report
w = WF("TableFlow 08 - Daily management reporting", ["tableflow", "reporting"])
a = schedule(w, "0 7 * * 1-6", "Mon-Sat 07:00 SAST")
b = token(w)
c = api(w, "Daily summary", "GET", "/api/v1/automation/daily-summary")
d = api(w, "Open incidents", "GET", "/api/v1/incidents", query={"open_only": "true", "limit": "20"})
e = code(w, "Compose report", """const s = $('Daily summary').first().json;
const inc = $input.first().json;
const zar = n => 'R' + Number(n).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const top = (s.branches || []).sort((a, b) => b.revenue - a.revenue).slice(0, 3)
  .map(b => `${b.name} ${zar(b.revenue)} (${b.orders} orders)`).join('; ');
const down = (s.integration_health.items || []).filter(i => i.status !== 'healthy').map(i => `${i.name}: ${i.status}`);
const text = [`*TableFlow daily report - ${s.business_date}*`,
  `Sales ${zar(s.total_sales_zar)} from ${s.total_orders} orders (avg ${zar(s.average_order_value_zar)})`,
  `Payments: ${s.payments.successful} ok / ${s.payments.failed} failed (${s.payments.success_rate}% success)`,
  `Top branches: ${top || 'n/a'}`,
  `Integrations needing attention: ${down.length ? down.join(', ') : 'none'}`,
  `Open incidents: ${inc.total}`].join('\\n');
return [{ json: { text } }];""")
f = alert(w, "Send to management channel", "#management", "$json.text")
w.chain(a, b, c, d, e, f)
workflows.append(("08_daily_management_reporting", w))

OUT.mkdir(parents=True, exist_ok=True)
for fname, wf in workflows:
    (OUT / f"{fname}.json").write_text(json.dumps(wf.to_json(), indent=2))
print(f"wrote {len(workflows)} workflows to {OUT}")
