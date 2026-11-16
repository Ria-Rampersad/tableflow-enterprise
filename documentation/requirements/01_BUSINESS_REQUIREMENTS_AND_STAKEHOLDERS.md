# 01 · Business Requirements Document, Scope, Stakeholders & Interview Notes

> **Fictional scenario.** "Shisa Flame Chicken" is an invented 12-branch South African restaurant group used to
> give this portfolio project a realistic business context. No real company data, people or systems are used.

## 1. Executive summary

Shisa Flame Chicken trades from 12 branches in KwaZulu-Natal, Gauteng, Western Cape, Eastern Cape and Free State.
Orders arrive in-store (Oracle MICROS Simphony POS), through Uber Eats and Mr D, and via the web. Card payments
go through a Transaction Junction-style switch. A loyalty platform awards points.

Each system works, but **nothing connects them**. Delivery orders are re-keyed into the POS by cashiers at peak
time, Finance reconciles payments to bank settlements in spreadsheets two to four days late, and when an
integration fails nobody knows until a branch manager phones Head Office.

**TableFlow Enterprise** is the requested solution: one integration and operations platform that moves orders
and payments between systems automatically, reconciles them every morning, alerts the right people when
something breaks, and gives management a single view of the business.

## 2. Problem statement (current pain, quantified from the stakeholder interviews)

| # | Problem | Who feels it | Impact (stakeholder estimate) |
|---|---|---|---|
| P1 | Delivery orders re-keyed from tablets into Simphony | Branch staff | 2–4 min per order at peak; ~3% keying errors; delayed kitchen tickets |
| P2 | Manual payment ↔ settlement reconciliation in Excel | Finance | ~2 FTE days per week; discrepancies found 2–4 days late |
| P3 | Integration failures discovered by phone calls | Operations / IT | Outages of 30–90 minutes before anyone acts |
| P4 | No duplicate protection when providers retry | Finance, customers | Occasional double orders / double charges |
| P5 | Loyalty points silently lost when the loyalty platform times out | Marketing, customers | Customer complaints; no record to replay |
| P6 | No single view of sales, payment success and integration health | Management | Decisions made on week-old spreadsheets |
| P7 | No audit trail of refunds and configuration changes | Finance, Audit | Audit findings; fraud risk |

## 3. Business objectives & success measures

| Objective | KPI | Target |
|---|---|---|
| Eliminate re-keying of digital orders | % digital orders reaching POS automatically | ≥ 99% |
| Same-day financial visibility | Reconciliation available by | 06:30 SAST next day |
| Detect integration failures before branches call | Time to automated alert | < 5 minutes |
| Prevent duplicate orders/charges | Duplicates created from provider retries | 0 |
| Never lose loyalty points | Points without a ledger entry | 0 |
| Accountability | State changes with an audit entry | 100% |

## 4. Scope

**In scope (this release)**
- Executive dashboard; branch management; POS (Simphony) adapter; Uber Eats & Mr D adapters; payment
  (Transaction Junction-style) adapter; loyalty adapter; finance GL and back-office inventory adapters.
- Webhook ingestion with signature verification, de-duplication and replay.
- Integration monitoring, automatic incident creation, incident management.
- Daily reconciliation (orders × payments × POS × settlements), CSV export, settlement import.
- n8n automation (8 workflows), reporting (9 reports), Snowflake analytical model.
- Role-based access, OAuth 2.0 / JWT, audit trail, Docker deployment, CI pipeline.

**Out of scope**
- Live vendor connectivity (requires commercial agreements and sandbox credentials — all adapters are simulated).
- Card data handling: TableFlow only ever sees **tokens**; PAN never enters the system (keeps PCI DSS scope minimal).
- Menu authoring, kitchen display, payroll, stock purchasing.
- Production hosting (no environment exists; see the DevOps handbook).

**Assumptions**: branches trade 10:00–22:00 SAST; prices are VAT-inclusive (15%); providers retry webhooks on
non-2xx; settlement files arrive T+1.

**Constraints**: small team (one Solutions Engineer); must run on a laptop via Docker Compose; no vendor credentials.

## 5. Stakeholder analysis

| Stakeholder | Role | Interest | Influence | Engagement approach |
|---|---|---|---|---|
| Head of Product (Product Owner) | Prioritises backlog, signs off scope | High | High | Weekly demo; owns acceptance criteria |
| Financial Controller | Owns reconciliation & refunds | High | High | Co-design reconciliation rules; UAT sign-off |
| Operations Manager | Branch performance, incidents | High | Medium | Alerting design; incident process |
| Branch Managers (Umhlanga, Sandton) | Daily trading | Medium | Low | Interviews, UAT on branch screens |
| Integration / IT Lead | Vendor relationships, security | High | High | Architecture review; security review |
| Marketing (Loyalty) | Points accuracy | Medium | Medium | Loyalty rules confirmation |
| External vendors (Oracle, TJ, Uber, Mr D) | API contracts | Low | High | Sandbox requests (out of scope now) |

RACI for this release: **Responsible** – Solutions Engineer; **Accountable** – Product Owner;
**Consulted** – Finance, Operations, IT Lead; **Informed** – Branch Managers, Marketing.

## 6. Stakeholder interview notes (examples of requirements gathering)

**Interview 1 — Financial Controller (Finance)**
- "Every Monday two people spend the morning matching the TJ settlement CSV to our sales export."
- "What hurts is the R1.50 short-pays and the missing lines — we find them days later."
- "I need to know: paid but not on settlement; on settlement but we have no sale; charged twice."
- *Follow-up question asked:* "How do you identify a transaction on both sides?" → gateway reference.
- → Requirements **FR-REC-01..06**, business rules **BR-REC-01..03**, CSV import/export.

**Interview 2 — Operations Manager**
- "When Simphony is down at a branch, Uber orders just vanish until someone notices."
- "I don't want an email for every failed card — I want to know when it's a *pattern*."
- → Retry with back-off, **auto-incident after 3 consecutive failures**, n8n alerts with thresholds (≥ R500,
  ≥ 3 stuck orders), severity model SEV1–SEV4.

**Interview 3 — Branch Manager, Umhlanga**
- "Sometimes Uber sends the same order twice and the kitchen makes it twice."
- "I only care about my branch."
- → Idempotent ingest on (channel, external_ref); branch-scoped data for the `branch_manager` role.

**Interview 4 — Integration / IT Lead**
- "No passwords for service accounts. No secrets in Git. Every webhook must be signed."
- "Snowflake access must use key-pair auth."
- → OAuth 2.0 client credentials for n8n, `.env`-based secrets, HMAC verification, RSA key-pair module.

**Interview 5 — Product Owner**
- "Phase 1 must prove the integration patterns on simulated vendors; real sandboxes come after contracts."
- → All adapters explicitly marked `mode = simulated`; sandbox-ready adapter interface.

### Translating a need into a specification (worked example)
| Step | Output |
|---|---|
| Business need (Finance) | "Tell me when we were charged twice." |
| Clarified rule | Two or more *captured* payments for one order on the same business day |
| Data needed | payments.order_id, payments.status, payments.provider_reference |
| Functional requirement | FR-REC-03: reconciliation flags `duplicate_payment` with all gateway references |
| Acceptance criterion | Given an order with two captured payments, when reconciliation runs, then one `duplicate_payment` record lists both references |
| Test | `test_reconciliation_matching_logic_detects_every_issue_type` |

## 7. Complexity assessment & escalation to a larger engineering team

Each request is scored 1–3 on five dimensions; **total ≥ 11, or any 3 in "Security/PCI" or "Vendor contract",
means the Solutions Engineer scopes it and hands it to the Engineering team.**

| Dimension | 1 | 2 | 3 |
|---|---|---|---|
| Systems touched | 1 | 2–3 | 4+ |
| Data sensitivity | none | PII | card data / money movement |
| Vendor dependency | none | documented API | contract / certification needed |
| Volume / performance | < 1k/day | < 100k/day | real-time at scale |
| Reversibility | trivial | needs migration | irreversible |

| Initiative | Score | Decision |
|---|---|---|
| Low-stock n8n alert | 1+1+1+1+1 = 5 | Solutions Engineer builds end-to-end |
| Daily reconciliation | 3+2+1+2+2 = 10 | Solutions Engineer builds, Finance co-owns rules |
| Live Simphony integration | 2+2+3+3+2 = 12 | **Escalate**: vendor certification + scale |
| In-house card tokenisation | 2+3+3+3+3 = 14 | **Escalate**: PCI DSS scope; never build in-house |

## 8. Risks (summary — full register in `07_PROJECT_RISK_ASSESSMENT.md`)
Vendor API contracts differ from the simulation; webhook secret rotation; data quality in settlement files;
single-person dependency; scope creep into POS/menu management.
