#!/usr/bin/env node
/**
 * n8n-local-runner - executes TableFlow's n8n workflow JSON files WITHOUT an n8n server.
 *
 * Purpose: a local demonstration and CI smoke test for environments where n8n
 * (or Docker) is not available. It is NOT n8n. It implements only the subset of
 * node types the TableFlow workflows use:
 *   webhook, scheduleTrigger, httpRequest, if (v2), code (JavaScript), wait (skipped), noOp
 * and the expression syntax they rely on: ={{ ... }} with $json, $env, $('Node'), $input, $now.
 * In production, import the same JSON files into a real n8n instance (see automation/README.md).
 *
 * Usage:
 *   node n8n-local-runner.mjs <workflow.json> [--payload '{"json":"body"}'] [--quiet]
 * Environment: TABLEFLOW_API_URL, TABLEFLOW_CLIENT_ID, TABLEFLOW_CLIENT_SECRET, ALERT_WEBHOOK_URL, ALERT_TOKEN
 */
import { readFileSync } from 'node:fs';

const args = process.argv.slice(2);
if (!args[0]) { console.error('usage: n8n-local-runner.mjs <workflow.json> [--payload JSON]'); process.exit(2); }
const wf = JSON.parse(readFileSync(args[0], 'utf8'));
const pIdx = args.indexOf('--payload');
const payload = pIdx >= 0 ? JSON.parse(args[pIdx + 1]) : {};
const quiet = args.includes('--quiet');

const nodes = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
const runData = {};               // node name -> output items (all outputs flattened)
const trace = [];

function nodeAccessor(name) {
  const items = runData[name];
  if (!items) throw new Error(`Expression references node '${name}' which has not run`);
  return { first: () => items[0], last: () => items[items.length - 1], all: () => items, item: items[0] ?? { json: {} } };
}

function evaluate(value, item, idx = 0) {
  if (typeof value !== 'string' || !value.startsWith('=')) return value;
  const src = value.slice(1);
  const ctx = (expr) => {
    const fn = new Function('$json', '$env', '$', '$input', '$now', `return (${expr});`);
    const $ = (name) => {
      const acc = nodeAccessor(name);
      return { ...acc, item: runData[name][idx] ?? acc.item };
    };
    return fn(item?.json ?? {}, process.env, $, { first: () => item, all: () => [item] }, new Date());
  };
  const whole = src.match(/^\{\{([\s\S]*)\}\}$/);
  if (whole && !whole[1].includes('}}')) return ctx(whole[1]);
  return src.replace(/\{\{([\s\S]*?)\}\}/g, (_, e) => String(ctx(e)));
}

async function runCode(node, items) {
  const $input = { all: () => items, first: () => items[0], last: () => items[items.length - 1], item: items[0] };
  const $ = (name) => nodeAccessor(name);
  const fn = new Function('$input', '$', '$env', `return (async () => { ${node.parameters.jsCode} })();`);
  const out = await fn($input, $, process.env);
  return [out.map((o) => ('json' in o ? o : { json: o }))];
}

async function runHttp(node, items) {
  const p = node.parameters;
  const out = [];
  for (const [i, item] of items.entries()) {
    try {
      let url = evaluate(p.url, item, i);
      const headers = {};
      for (const h of p.headerParameters?.parameters ?? []) headers[h.name] = evaluate(h.value, item, i);
      if (p.sendQuery) {
        const q = new URLSearchParams();
        for (const qp of p.queryParameters.parameters) q.set(qp.name, evaluate(qp.value, item, i));
        url += (url.includes('?') ? '&' : '?') + q.toString();
      }
      let body;
      if (p.sendBody && p.contentType === 'form-urlencoded') {
        const f = new URLSearchParams();
        for (const bp of p.bodyParameters.parameters) f.set(bp.name, evaluate(bp.value, item, i));
        body = f.toString();
        headers['Content-Type'] = 'application/x-www-form-urlencoded';
      } else if (p.sendBody && p.specifyBody === 'json') {
        const b = evaluate(p.jsonBody, item, i);
        body = typeof b === 'string' ? b : JSON.stringify(b);
        headers['Content-Type'] = 'application/json';
      }
      const res = await fetch(url, { method: p.method ?? 'GET', headers, body });
      const text = await res.text();
      let json; try { json = JSON.parse(text); } catch { json = { body: text }; }
      if (!res.ok) throw new Error(`HTTP ${res.status} ${p.method} ${url}: ${text.slice(0, 300)}`);
      out.push({ json: Array.isArray(json) ? { items: json } : json });
    } catch (err) {
      if (node.onError === 'continueRegularOutput') out.push({ json: { error: String(err.message) } });
      else throw err;
    }
  }
  return [out];
}

function runIf(node, items) {
  const t = [], f = [];
  const cfg = node.parameters.conditions;
  items.forEach((item, i) => {
    const results = cfg.conditions.map((c) => {
      const l = evaluate(c.leftValue, item, i);
      const r = c.rightValue === undefined ? undefined : evaluate(c.rightValue, item, i);
      const op = c.operator.operation;
      switch (op) {
        case 'equals': return String(l) === String(r);
        case 'notEquals': return String(l) !== String(r);
        case 'gt': return Number(l) > Number(r);
        case 'gte': return Number(l) >= Number(r);
        case 'lt': return Number(l) < Number(r);
        case 'lte': return Number(l) <= Number(r);
        case 'true': return l === true || l === 'true';
        case 'false': return l === false || l === 'false';
        case 'contains': return String(l).includes(String(r));
        case 'exists': return l !== undefined && l !== null;
        default: throw new Error(`IF operator '${op}' not supported by local runner`);
      }
    });
    const pass = cfg.combinator === 'or' ? results.some(Boolean) : results.every(Boolean);
    (pass ? t : f).push(item);
  });
  return [t, f];
}

async function execute(node, items) {
  switch (node.type) {
    case 'n8n-nodes-base.webhook': return [[{ json: { body: payload, headers: {}, query: {} } }]];
    case 'n8n-nodes-base.scheduleTrigger': return [[{ json: { timestamp: new Date().toISOString() } }]];
    case 'n8n-nodes-base.code': return runCode(node, items);
    case 'n8n-nodes-base.httpRequest': return runHttp(node, items);
    case 'n8n-nodes-base.if': return runIf(node, items);
    case 'n8n-nodes-base.wait': return [items]; // not waited locally - noted in trace
    case 'n8n-nodes-base.noOp': return [items];
    default: throw new Error(`Node type ${node.type} not supported by local runner`);
  }
}

const trigger = wf.nodes.find((n) => /webhook|scheduleTrigger/.test(n.type));
const queue = [[trigger.name, []]];
let failed = false;
while (queue.length) {
  const [name, items] = queue.shift();
  const node = nodes[name];
  try {
    const outputs = await execute(node, items);
    runData[name] = outputs.flat();
    trace.push({ node: name, in: items.length, out: outputs.map((o) => o.length),
                 note: node.type.endsWith('.wait') ? 'wait skipped by local runner' : undefined });
    const conns = wf.connections[name]?.main ?? [];
    conns.forEach((targets, outIdx) => {
      const outItems = outputs[outIdx] ?? [];
      if (!outItems.length) return;
      for (const t of targets) queue.push([t.node, outItems]);
    });
  } catch (err) {
    failed = true;
    trace.push({ node: name, error: err.message });
    break;
  }
}

if (!quiet) {
  console.log(`\nWorkflow: ${wf.name}`);
  for (const t of trace) {
    console.log(t.error ? `  x ${t.node}: ${t.error}` : `  - ${t.node}: in=${t.in} out=${JSON.stringify(t.out)}${t.note ? ' (' + t.note + ')' : ''}`);
  }
}
console.log(JSON.stringify({ workflow: wf.name, ok: !failed, nodes_run: trace.length }));
process.exit(failed ? 1 : 0);
