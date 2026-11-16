# 11 · AI-Assisted Development (Claude, GitHub Copilot, Cursor)

AI tools speed up a Solutions Engineer's work, but responsibility for correctness, security and honesty stays
with the engineer. This project was generated with substantial help from **Claude**; GitHub Copilot and Cursor are
described as they would fit the same workflow. Nothing generated was assumed correct — it was run, tested and fixed.

## Where each tool helps
| Activity | Claude (chat/agent) | GitHub Copilot (inline) | Cursor (AI editor) |
|---|---|---|---|
| Requirements | turn interview notes into user stories, Gherkin, business rules | — | — |
| Design | compare options (outbox vs inline calls), draft ADRs, Mermaid diagrams | — | ask questions about the whole repo |
| Code generation | scaffold modules, adapters, SQL, workflows | complete repetitive code (columns, test params) | multi-file edits ("add Bolt Food adapter like Uber") |
| Debugging | explain tracebacks, propose hypotheses | — | inline fix suggestions with repo context |
| Testing | propose negative/edge cases, fixtures | complete test bodies | generate tests next to code |
| Documentation | draft handbooks, runbooks from code | docstrings | update docs alongside code |

## Example prompts that work well
- "Here are notes from the Financial Controller interview. List the discrepancy types they care about, define each precisely, and propose acceptance criteria with concrete Rand values."
- "Review `services/orders.py:ingest` for race conditions when the same provider order arrives twice concurrently."
- "Write pytest cases for the payment endpoint: approve, each decline code, retryable error, idempotent replay, idempotency conflict, missing header, amount mismatch, RBAC."
- "This migration fails with `only '%s', '%b', '%t' are allowed as placeholders`. Explain why and propose the minimal fix."

## Critical human review — what was checked
1. **Does it run?** Every component was executed: pytest on SQLite *and* PostgreSQL, Vitest, ESLint, tsc, Newman, the n8n runner, the ELT, SQL queries, a headless-browser pass over every screen.
2. **Is it secure?**
   - Every endpoint has an auth dependency (contract: unauthenticated request returns 401; RBAC tests for 403).
   - No secrets in code — defaults are obvious `dev-…-change-me` values and `.env` is git-ignored.
   - Ruff `S` (bandit) rules run in CI. Findings reviewed individually: SHA-1 for a demo check number (not security), `"user"` flagged as a hardcoded password (it's a claim type), f-string SQL in seed/ELT (identifiers from code constants, never user input). Each annotated with the reason rather than disabling the rule.
   - Webhook verification uses constant-time comparison; card data never accepted.
3. **Is it correct for the business?** VAT maths checked by hand (R164.70 → VAT R21.48); reconciliation tested with one order per issue type and exact differences.
4. **Is it honest?** Simulations labelled in code, UI ("Simulated" tags, `mode=simulated`) and docs; unverified items (Docker run, GitHub Actions, Snowflake account, n8n server) listed in the Verification Report.

## Examples where generated code was wrong or incomplete
| Generated assumption | What actually happened | Lesson |
|---|---|---|
| `exec_driver_sql` can run any migration file | psycopg parsed `%` in PL/pgSQL as a placeholder | test against the real database engine |
| `EmailStr` is fine for user emails | rejects reserved `.local` domains used by the demo | read validator semantics; test the happy path end to end |
| `app.routes` lists all endpoints | newer FastAPI nests routers | don't rely on framework internals; use the public OpenAPI contract |
| Postman: set token as collection variable | environment variable of the same name takes precedence | understand tool scoping rules |
| Seeding a "short payment" by subtracting a fixed amount | negative amounts on cheap orders | constraints catch what generators miss |

## Guidelines I follow
- Never paste credentials, customer data or proprietary code into tools outside company policy.
- Ask for small, reviewable changes; read every line before committing.
- Require a failing test before accepting a bug fix; keep the test as a regression guard.
- Prefer explanations over magic — if I can't explain the generated code in an interview, I don't ship it.
