# User Acceptance Testing (UAT) Pack

Environment: UAT stack seeded with `SEED_DEMO_DATA=true`. Logins in README. Record **Actual result**, **Pass/Fail**,
tester initials and date. Defects use the template in Doc 06 §10. The *Actual* column is intentionally blank —
UAT is executed by business users; developer pre-checks are noted in the last column.

## Restaurant managers (login: manager.umhlanga@tableflow.local)
| ID | Scenario | Steps | Expected result | Actual | P/F | Dev pre-check |
|---|---|---|---|---|---|---|
| UAT-BM-01 | See only my branch's orders | Orders screen, no filter | Only Umhlanga Gateway orders listed | | | ✅ API test |
| UAT-BM-02 | Progress an order | Open an accepted order → Mark preparing → ready → completed | Status follows; invalid steps not offered | | | ✅ |
| UAT-BM-03 | Cancel requires a reason | Cancel without a reason | Message asking for a reason; order unchanged | | | ✅ |
| UAT-BM-04 | Take a card payment | New in-store order → Take payment (tok_visa_approved) | Payment captured; loyalty points added if phone is a member | | | ✅ |
| UAT-BM-05 | Branch performance | Dashboard → click Umhlanga in branch table | Branch page with sales chart and top products | | | 👁 |

## Finance (login: finance@tableflow.local)
| ID | Scenario | Steps | Expected result | Actual | P/F | Dev pre-check |
|---|---|---|---|---|---|---|
| UAT-FIN-01 | Daily reconciliation | Reconciliation → yesterday → Reconcile | Orders/matched/discrepancies/value shown; each issue has details | | | ✅ |
| UAT-FIN-02 | Export for audit | Export CSV | CSV opens in Excel with one row per record | | | ✅ |
| UAT-FIN-03 | Import settlement file | Import `integrations/transaction_junction/sample_settlement.csv` twice | First: inserted 1; second: skipped duplicate 1 | | | ✅ |
| UAT-FIN-04 | Partial refund | Payments → captured payment → refund R20 with reason | Status partially refunded; audit entry with your email | | | ✅ |
| UAT-FIN-05 | Over-refund blocked | Refund more than remaining | Error "exceeds refundable balance"; nothing changes | | | ✅ |
| UAT-FIN-06 | Reports | Reports → Payment success → Download CSV | Branches with success %, CSV downloads | | | ✅ |

## Operations (login: ops@tableflow.local; engineer@ for outage simulation)
| ID | Scenario | Steps | Expected result | Actual | P/F | Dev pre-check |
|---|---|---|---|---|---|---|
| UAT-OPS-01 | POS outage handling | (engineer) Simulate Simphony outage → send 3 Uber orders | Orders failed; Simphony down; one SEV2 incident; POS alert in outbox | | | ✅ |
| UAT-OPS-02 | Recover failed orders | End outage → POS Hub → Retry | Orders accepted | | | ✅ |
| UAT-OPS-03 | Incident lifecycle | Create SEV2 → assign → investigating → escalate → resolve with RCA | Timeline shows each step; cannot resolve without notes | | | ✅ |
| UAT-OPS-04 | Duplicate delivery order | Digital Ordering → send → re-send same | Second shows "Duplicate order ignored"; one order exists | | | ✅ |

## Administrators (login: admin@tableflow.local)
| ID | Scenario | Steps | Expected result | Actual | P/F | Dev pre-check |
|---|---|---|---|---|---|---|
| UAT-ADM-01 | Create branch with validation | New branch with code "durban" → fix to "DBN-GTW" | Format error first; then created and listed | | | ✅ |
| UAT-ADM-02 | Assign POS & channels | Branch detail → Edit → set location ref & channels | Saved; audit trail shows `branch.updated` | | | ✅ |
| UAT-ADM-03 | Audit trail | Audit Trail → filter entity "payment" | Entries with actor, action, IP, correlation id | | | ✅ |

## Sign-off
| Role | Name | Decision (Accept / Accept with conditions / Reject) | Conditions / open defects | Signature | Date |
|---|---|---|---|---|---|
| Product Owner | | | | | |
| Financial Controller | | | | | |
| Operations Manager | | | | | |
| Branch Manager representative | | | | | |
| IT / Integration Lead | | | | | |

Exit criteria: all UAT scenarios pass or have accepted workarounds; no open S1/S2 defects; Finance and Operations sign-off recorded.
