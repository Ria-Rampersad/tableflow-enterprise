# 07 · Project Risk Assessment

Likelihood (L) and Impact (I) scored 1–5; Score = L × I. ≥ 15 = high.

| ID | Risk | L | I | Score | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|
| R1 | Real vendor APIs differ from the simulated contracts | 4 | 4 | 16 | Adapter boundary isolates change; canonical model; contract tests; budget a sandbox phase per vendor | Solutions Eng. | Open – inherent to portfolio scope |
| R2 | Webhook signing secret rotated by provider without notice | 3 | 4 | 12 | Rejected events stored; alert on rejection spike; secrets via env/secret manager; runbook RB-04 | IT Lead | Mitigated |
| R3 | Duplicate charges from terminal/provider retries | 3 | 5 | 15 | Idempotency-Key + UNIQUE constraints; reconciliation `duplicate_payment` | Finance | Mitigated |
| R4 | Settlement file format changes | 3 | 3 | 9 | CSV import validates headers, reports per-line errors, is idempotent | Finance | Mitigated |
| R5 | Single engineer (key-person dependency) | 4 | 4 | 16 | Handbooks, runbooks, automated tests, CI; complexity rule for escalation | Product Owner | Mitigated (documentation) |
| R6 | Scope creep into POS/menu management | 3 | 3 | 9 | Signed scope; change control via Product Owner | Product Owner | Monitored |
| R7 | PCI DSS scope expansion if card data handled | 2 | 5 | 10 | Tokens only; never log PAN; payment UI owned by gateway | IT Lead | Mitigated by design |
| R8 | In-process rate limiter/metrics insufficient for multiple replicas | 3 | 2 | 6 | Documented upgrade path (Redis, Prometheus) | Solutions Eng. | Accepted |
| R9 | n8n outage hides alerts | 2 | 4 | 8 | Outbox keeps events; dashboard shows failures independently | Ops | Mitigated |
| R10 | POPIA (customer phone/email) | 3 | 4 | 12 | Minimal PII; role-based access; audit; retention policy to be defined | IT Lead | Partially mitigated |
| R11 | Snowflake cost overrun | 2 | 3 | 6 | XSMALL warehouse, 60 s auto-suspend, incremental loads | Finance | Mitigated |
| R12 | Clock skew breaks webhook timestamp checks | 2 | 3 | 6 | 300 s tolerance; NTP on hosts | IT Lead | Mitigated |
