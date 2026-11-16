# 08 · Solutions Engineering Interview Handbook (Pedros Solutions Engineer role)

How to use this: read the answer, then explain it out loud using an example from TableFlow. Interviewers probe
understanding — "show me where" is a common follow-up, so file pointers are included. Answers describe your
**portfolio project**; never present it as production experience.

The advertised role (from the public job listing): a Solutions Engineer in the Product team who delivers small
projects end to end across integrations and internal tools — requirements → build → testing → release — working
with Product Owners and business stakeholders, connecting POS, digital ordering, payment and back-office systems,
building tools for Stores, Operations and Finance with Python (FastAPI), React, TypeScript, PostgreSQL and n8n,
querying Snowflake and operational databases, and scoping larger initiatives for the Engineering team.

---

## A. Python (1–8)
**1. What are Python's main data types and when do you use each?** int/float/Decimal for numbers (Decimal for money), str, bool, list (ordered, mutable), tuple (immutable, e.g. constraint value lists), dict (key→value, e.g. JSON payloads), set (membership/de-dupe, e.g. `seen_refs` in reconciliation). Choosing the right one avoids bugs — a set makes "have I seen this reference?" O(1).

**2. Why `Decimal` instead of `float` for Rand amounts?** Floats are binary approximations (0.1 + 0.2 = 0.30000000000000004). Reconciliation compares amounts to the cent, so a float error would show as a false discrepancy. TableFlow uses `NUMERIC(12,2)` in SQL, `Decimal` in Python and strings in JSON; `Decimal(str(x))` avoids importing float error.

**3. Explain exceptions and how you used custom ones.** Exceptions signal that normal flow can't continue. I defined `AdapterError` (with `retryable` and `http_status`) so the IntegrationRunner can decide to retry, and `BusinessRuleError` (with `code` and `status_code`) so a global FastAPI handler returns a consistent JSON error. Catch specific exceptions, not bare `except`.

**4. What is a context manager?** An object with `__enter__/__exit__` used with `with` to guarantee cleanup. Examples: `with SessionLocal() as db` closes the session; `with db.begin_nested()` creates a savepoint that rolls back automatically if the block raises; `with engine.begin()` commits or rolls back a migration.

**5. What are type hints good for if Python doesn't enforce them?** Readability, IDE help, static checks, and — crucially — frameworks use them at runtime: FastAPI/Pydantic validate requests from the hints, and SQLAlchemy 2 maps `Mapped[int]` to columns.

**6. What is a decorator?** A function that wraps another to add behaviour. FastAPI's `@router.post(...)` registers a route; `@pytest.mark.regression` tags tests; `@lru_cache` caches `get_settings()`.

**7. Sync vs async in Python — when does async help?** Async helps when you wait on I/O and want to serve others meanwhile. TableFlow's n8n dispatcher is async (`httpx.AsyncClient`). DB code is sync, so those endpoints are plain `def` — FastAPI runs them in a threadpool. Mixing a blocking call inside an `async def` would freeze the event loop.

**8. How do you manage dependencies and environments?** Virtual env per project, pinned `requirements.txt` for runtime and `requirements-dev.txt` for tools; Docker image installs only runtime deps (multi-stage). CI uses pip caching.

## B. FastAPI (9–15)
**9. Walk me through a request in your FastAPI app.** Middleware assigns `X-Request-ID` and starts a timer → router matches the path → dependencies run (DB session, auth, RBAC, rate limit) → Pydantic validates the body → the handler calls a service → service flushes, handler commits → response model serialises → middleware records metrics and logs a JSON line. Errors at any step become the standard error envelope.

**10. What is dependency injection in FastAPI?** Parameters declared with `Depends(fn)` are resolved by FastAPI per request. `require_roles("finance")` is a dependency factory returning a checker; tests can override dependencies. It keeps auth and DB plumbing out of business code.

**11. How does FastAPI produce Swagger docs?** It builds an OpenAPI schema from routes, type hints, Pydantic models, tags and summaries; `/docs` renders it. I exported it to `documentation/api/openapi.json`, and a contract test checks Postman and n8n against it.

**12. How do you return different status codes?** `status_code=201` on the decorator; `response.status_code = 200` for idempotent replays; `HTTPException(409, ...)` or a `BusinessRuleError` for rule violations; 202 for partner orders processed in the background.

**13. What are BackgroundTasks and when not to use them?** Functions run after the response is sent, in the same process. I use them to forward partner orders to the POS so Uber gets a fast 202. Not for long or must-not-lose work — if the process dies the task is lost — so the order is committed *before*, and failed forwards are visible and retryable. For heavy work use a queue/worker.

**14. How do you handle CORS?** `CORSMiddleware` with allowed origins from env. In practice the SPA is served through nginx on the same origin, so CORS isn't even needed in Docker.

**15. How do you version an API?** URL prefix `/api/v1`; additive changes don't need a new version; breaking changes go to `/v2` while `/v1` is supported for a deprecation period.

## C. React (16–21)
**16. Explain components, props and state.** Components are functions returning UI; props are inputs from the parent; state (`useState`) is data the component owns that triggers re-render. `Kpi` takes `label/value/tone/onClick` props; the Dashboard holds date-range state.

**17. What does `useEffect` do and what's the classic bug?** Runs side effects after render when dependencies change. Classic bugs: missing dependencies (stale data) or setting state from an old request after a newer one. My `useApi` hook uses a sequence counter to ignore stale responses.

**18. How do you show loading and error states?** `useApi` returns `{data, loading, error, reload}`; pages render `<Spinner/>`, `<ErrorBox error onRetry/>` (with validation details and correlation reference) or `<Empty/>`.

**19. How do you validate forms?** Client-side for fast feedback (`validateBranch`, refund bounds, phone format, login email/password) and server-side as the source of truth (Pydantic). The UI shows server validation details too.

**20. How did you structure the frontend?** `services` (API client, types), `hooks`, `components` (DataTable, UI primitives, Layout), `pages` (one per module, lazy-loaded), `utils` (formatting), `tests`.

**21. How do you protect routes?** `RequireAuth` redirects to `/login` without a token; the API is the real enforcement (401/403); a 401 clears the session and redirects. Menu items are hidden by role, but hiding is UX, not security.

## D. TypeScript (22–25)
**22. Why TypeScript?** Catches mistakes before runtime (wrong field names, missing props), documents API shapes (`types.ts`), and makes refactors safe. `strict` mode and `tsc --noEmit` run in CI.

**23. `interface` vs `type`?** Both describe shapes; interfaces can be extended/merged and suit object contracts; `type` handles unions and mapped types. I used interfaces for API models.

**24. What are generics? Example?** Type parameters: `DataTable<T>` works for orders, payments or incidents with type-safe column renderers; `api.get<Paged<Order>>()` types the response.

**25. Does TypeScript validate API data at runtime?** No. Types vanish after compilation; runtime validation is on the server, or use a schema library (zod) on the client.

## E. SQL & PostgreSQL (26–37)
**26. INNER vs LEFT JOIN?** Inner keeps only matching rows; left keeps all left rows with NULLs for missing matches. "Captured but not settled" is a LEFT JOIN from payments to settlements `WHERE s.id IS NULL` (anti-join).

**27. WHERE vs HAVING?** WHERE filters rows before grouping; HAVING filters groups after aggregation — e.g. orders `HAVING COUNT(captured payments) > 1` for duplicates.

**28. What is an index and when does it hurt?** A sorted structure that lets the DB find rows without scanning the table. It costs storage and slows inserts/updates. I index columns used constantly in filters (`branch_id, created_at`) and verified with `EXPLAIN` that the composite index is used.

**29. What is a partial index?** An index with a WHERE clause, e.g. only failed payments. It's tiny and perfect for "needs attention" queues.

**30. Explain transactions and ACID.** Atomic (all or nothing), Consistent (constraints hold), Isolated (concurrent transactions don't see each other's partial work), Durable (committed = survives crash). In TableFlow an order, its items, audit row and outbox row commit together.

**31. What is a savepoint and where did you use it?** A nested rollback point inside a transaction. Order insert (so a duplicate-race IntegrityError doesn't kill the whole transaction) and each webhook handler (so a failed handler doesn't discard the stored event).

**32. Window functions?** Calculations across related rows without collapsing them: running totals (`SUM() OVER (ORDER BY d)`), moving averages, `ROW_NUMBER() OVER (PARTITION BY branch ...)` for top-N, `LAG` for week-on-week growth.

**33. How do you prevent duplicate rows under concurrency?** A UNIQUE constraint is the only reliable guard; application checks race. Catch the violation and return the existing row.

**34. Primary vs foreign key; ON DELETE options?** PK uniquely identifies a row; FK references another table's PK. RESTRICT keeps history (can't delete a branch with orders), CASCADE removes owned children, SET NULL for optional links.

**35. How do you handle schema changes safely?** Versioned migrations, never edit applied ones, backward-compatible "expand/contract" so old and new app versions both work during deploys, rehearse on a copy, test drift in CI.

**36. A report is slow — what do you do?** Reproduce with real parameters, `EXPLAIN ANALYZE`, look for sequential scans and bad row estimates, add/adjust an index, rewrite (avoid functions on indexed columns), limit columns, or move it to the warehouse.

**37. How do you store JSON in Postgres and why?** `JSONB` for payloads (webhook bodies, integration request/response, audit details) — flexible, indexable, but business fields you filter on stay in proper columns.

## F. Snowflake (38–43)
**38. What is Snowflake and how is it different from Postgres?** A cloud data warehouse: columnar storage, separate compute (virtual warehouses) that auto-suspend, scales for big analytical scans. Postgres is optimised for many small transactional reads/writes.

**39. Why separate operational and analytical data?** Analytics scans millions of rows; running that on the order database slows trading. Snowflake also keeps history and joins data from many sources.

**40. ETL vs ELT?** ELT loads raw data first and transforms in-warehouse with SQL. Cheaper to change models, raw history retained, scales with the warehouse. TableFlow: Postgres → CSV → `PUT`/`COPY INTO RAW` → SQL to STAGING → ANALYTICS.

**41. How do you do incremental loads and avoid duplicates?** Extract rows with `updated_at > last watermark`; land them in RAW; in STAGING keep the latest version per id with `QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1`.

**42. What is a star schema?** Fact tables of events/measures (`fct_orders`, `fct_payments`) surrounded by dimensions (`dim_branch`, `dim_date`, `dim_product`). Simple joins, fast aggregates, friendly for BI tools.

**43. How do you control Snowflake cost and secure access?** Smallest warehouse that meets SLAs, auto-suspend 60 s, incremental loads, resource monitors; least-privilege roles (LOADER vs REPORTER) and key-pair auth for service users. In my project the Snowflake SQL was validated by running the same SQL on DuckDB locally — I haven't run it on a live Snowflake account and would say so.

## G. REST APIs (44–49)
**44. What makes an API RESTful?** Resources with URLs, standard methods, stateless requests, meaningful status codes, representations in JSON.

**45. Idempotency — define it and give examples.** Doing an operation twice has the same effect as once. GET/PUT/DELETE should be idempotent; POST isn't, so I add `Idempotency-Key` for payments and natural keys for provider orders and webhooks.

**46. 401 vs 403?** 401: we don't know who you are (missing/invalid token). 403: we know who you are but you're not allowed (branch manager trying to refund).

**47. How do you design error responses?** One envelope with machine code, human message, details and a correlation id. Clients branch on `code`; support uses `correlation_id`.

**48. How do you paginate?** `limit/offset` with `total` (simple, fine for this volume). For very large or fast-changing lists, cursor/keyset pagination (`WHERE id < last_id`) avoids skipping rows.

**49. How do you protect an API from abuse?** Authentication, RBAC, validation, rate limiting (sliding window → 429 with Retry-After), payload size limits at the proxy, logging/monitoring.

## H. Webhooks (50–54)
**50. How do you verify a webhook?** Recompute HMAC-SHA256 of the raw body with the shared secret and compare in constant time; for timestamped schemes also reject old timestamps (replay protection).

**51. Why verify on raw bytes?** Parsing and re-serialising JSON can change whitespace or key order, producing a different HMAC.

**52. Providers send the same webhook several times — how do you handle it?** Store `(source, event_id)` with a UNIQUE constraint; on repeat acknowledge 200 and don't reprocess; count attempts.

**53. What do you return when processing fails?** If retrying won't help (unknown transaction), store as failed, return 200, and replay after fixing data. If it's transient on our side (DB down), return 5xx so the provider retries.

**54. Webhook vs polling?** Webhooks push events immediately and save calls but need a public endpoint, security and idempotency. Polling is simpler but laggy and wasteful. I use webhooks for payments/cancellations and polling-style sync for POS closed checks.

## I. OAuth 2.0 & authentication (55–61)
**55. Explain the client-credentials flow.** A machine posts `client_id`/`client_secret` (and scopes) to the token endpoint and receives an access token, then calls APIs with `Authorization: Bearer`. n8n does exactly this in every workflow.

**56. Which OAuth flow for a browser SPA in production?** Authorization Code with PKCE via an identity provider. My demo uses the password grant because it's first-party and simple; I'd change it for production.

**57. What's inside a JWT and how is it verified?** Header (alg), payload (claims: sub, roles, exp, iss), signature. The server verifies the signature with the secret/public key and checks expiry and issuer before trusting claims.

**58. How do you revoke access with JWTs?** Short lifetimes, re-check user status per request (I do), refresh-token rotation, deny-lists for emergencies.

**59. How do you store passwords?** Never plain or reversibly encrypted — a slow salted hash (bcrypt cost 12). Two hashes of the same password differ.

**60. What is RBAC and how did you implement it?** Permissions attached to roles, users get roles. A dependency `require_roles(...)` on each endpoint; admin passes all; client scopes map to roles; branch managers are scoped to their branch's data.

**61. What is key-pair authentication?** The client proves possession of a private key; the server holds only the public key. Snowflake service users use it instead of passwords; I wrote key generation, DER export and fingerprinting.

## J. POS integrations (62–66)
**62. What does a POS integration need to do for delivery orders?** Create the order as a POS check at the right location/revenue centre with mapped menu items and order type, update status, and later pull closed checks/tenders for reconciliation.

**63. What's the most common POS integration failure?** Master-data mismatch — menu items or modifiers not mapped, or location codes wrong. My adapter returns a permanent 422 for unmapped items and menu sync lists them.

**64. How do you avoid losing orders when the POS is down?** Persist first, forward asynchronously with retries, mark failed, alert, provide retry tooling, and give branches a manual fallback.

**65. How would you move from simulated to real Simphony?** Get API access and a sandbox, map the org/location hierarchy and menu item numbers, implement the adapter's methods with HTTP and OAuth, run contract tests against the sandbox, pilot at one branch, then roll out.

**66. Why pull closed checks from the POS?** The POS is the record of what was actually rung up and tendered; comparing it with orders and payments catches staff overrides, voids and sync gaps.

## K. Payment processing (67–72)
**67. Authorisation vs capture vs settlement?** Authorisation reserves funds; capture claims them; settlement is the acquirer paying the merchant (usually T+1, minus fees). Reconciliation compares all three views.

**68. What are ISO 8583 response codes?** Standard codes in card messaging: 00 approved, 05 do not honour, 51 insufficient funds, 54 expired, 91 issuer unavailable. Declines aren't retried; 91 is.

**69. How do you prevent double charges?** Idempotency keys, unique gateway references, refuse to pay an order with no outstanding balance, reconciliation flags duplicates.

**70. What is PCI DSS and how did you stay out of scope?** The card-data security standard. TableFlow only accepts tokens from the gateway and masks them in logs; card numbers never touch our systems.

**71. How are refunds controlled?** Finance-only RBAC, can't exceed captured amount, every refund audited with reason and actor, gateway failure recorded and surfaced.

**72. How would you reconcile payments?** Match by gateway reference to settlement lines and by order id to orders; classify missing, duplicate, mismatched and unknown items; export for Finance; raise incidents above a value threshold.

## L. Digital ordering (73–76)
**73. How do you integrate two delivery platforms with different payloads?** Adapter per platform mapping into one canonical order; business rules apply once. Uber sends cents and UUIDs; Mr D sends Rand and its own references.

**74. What if the provider's total doesn't match our menu prices?** Platforms may mark up, so we accept their unit prices but require the total to equal the sum of lines (±R0.01); unknown SKUs are rejected.

**75. How do cancellations work?** Provider cancel endpoint or signed webhook → find by external reference → state-machine check → cancel with reason → push to POS → audit.

**76. Why respond 202 to partner orders?** Providers have short timeouts; we acknowledge receipt after persisting and process POS forwarding asynchronously.

## M. Loyalty (77–78)
**77. How do you ensure loyalty points are never lost?** Write the local ledger first, then sync; failures are stored and retried (UI or n8n). Unique constraint ensures one earn per order.

**78. Why must redemptions be confirmed by the platform first?** Otherwise a customer could spend points the system of record doesn't agree they have; if the platform is down we refuse (502) and don't deduct.

## N. n8n & automation (79–83)
**79. What is n8n and what did you build with it?** A self-hostable workflow tool. Eight workflows: failed payments, POS failures, new orders, loyalty retries, daily reconciliation, low stock, incident escalation with auto-escalate after 30 minutes, and a daily management report.

**80. How do n8n and your API communicate securely?** TableFlow pushes events to n8n webhooks from an outbox; n8n calls back with an OAuth2 client-credentials token restricted by scopes.

**81. What belongs in n8n vs in code?** Glue, notifications, schedules and thresholds that ops may tweak → n8n. Business rules, money movement, validation → tested code.

**82. What happens if n8n is down?** Events stay in the outbox as pending/failed and can be re-dispatched; the dashboard still shows failures independently.

**83. How did you test workflows without n8n?** Contract tests (structure, node connections, every API URL exists) and a small local runner that executed all eight against the live API. I'd still do a final test inside n8n itself.

## O. Postman & automated testing (84–89)
**84. How do you use Postman beyond manual calls?** Collections with environments and test scripts that chain variables, run in CI with Newman — 87 requests, 91 assertions passing.

**85. Unit vs integration vs end-to-end?** Unit: one function in isolation. Integration: components together (API + real Postgres). E2E: a business journey through public interfaces.

**86. Why run tests on both SQLite and Postgres?** SQLite is fast for development; Postgres proves the real migrations, constraints, triggers and SQL dialect. The Postgres-only tests caught issues SQLite never would.

**87. What is regression testing and how did you organise it?** Re-running tests to prove changes didn't break existing behaviour. Marked high-risk and bug-reproducing tests with `@pytest.mark.regression` and run them on every build.

**88. What is test coverage and is 100% the goal?** Lines executed by tests (92% backend). Not the goal itself — meaningful assertions on risky paths matter more than touching every line.

**89. How do you test external integrations you can't call?** Simulated adapters with deterministic failure knobs, contract tests against sample payloads, then sandbox tests when credentials exist.

## P. Docker, Git & CI/CD (90–95)
**90. Image vs container?** An image is the packaged filesystem + metadata; a container is a running instance.

**91. Why multi-stage builds and non-root users?** Smaller images without build tools; non-root limits damage if compromised.

**92. What does Docker Compose give you?** Multi-service local environments with networks, volumes, env and health-based start order in one file.

**93. Describe your CI pipeline.** Lint → tests (SQLite, Postgres, regression) → frontend lint/typecheck/test/build → Newman and workflow runs against a live API → Docker build and smoke test → gated deploy. Honest note: written and locally verified piece by piece, not yet run on GitHub.

**94. Merge vs rebase?** Merge preserves history with a merge commit; rebase rewrites commits on top of another branch for a linear history. Don't rebase shared branches.

**95. How do you roll back a bad release?** Redeploy the previous image tag; migrations designed to be backward compatible; feature flags for risky features.

## Q. Requirements, design & stakeholders (96–102)
**96. How do you gather requirements from Finance vs Operations?** Finance: walk through their spreadsheet and ask for examples of each discrepancy and how they identify a transaction. Operations: ask about the last outage — how they found out, what they did, what they wished they'd known.

**97. How do you turn "I need better visibility" into a spec?** Ask which decision they'd make, with which number, how often; define metric, source, filters, freshness; write acceptance criteria and a mock-up; confirm.

**98. How do you decide if a project is too big for you?** A complexity score: systems touched, data sensitivity, vendor certification, volume, reversibility. Card data or vendor certification → scope and hand to Engineering.

**99. How do you handle conflicting stakeholder priorities?** Make trade-offs explicit (impact, effort, risk), let the Product Owner decide, document the decision, and deliver something usable early for each.

**100. What's in a good acceptance criterion?** Testable Given/When/Then with concrete values, including the negative path — e.g. over-refund returns 422 and nothing changes.

**101. How do you document a solution?** BRD, rules, architecture diagrams, API spec, runbooks, test evidence, and a traceability matrix linking requirements to code and tests.

**102. How do you manage scope creep?** Signed scope with explicit out-of-scope items, change requests via the Product Owner, impact assessment before saying yes.

## R. UAT & production releases (103–106)
**103. How do you run UAT?** Persona-based scripts with expected results, real-looking data, business users execute and record actual results, defects triaged, formal sign-off.

**104. What do you check before a production release?** Green CI, regression pack, UAT sign-off, migration rehearsal, rollback plan, comms to branches, deploy outside peak, monitoring ready.

**105. How do you release a change that touches payments?** Finance sign-off, feature flag or pilot branch, extra monitoring on success rate and reconciliation, rollback ready.

**106. What would you monitor right after release?** Error rate, p95 latency, payment success rate, failed POS forwards, webhook rejections, new incidents.

## S. Monitoring, incidents & RCA (107–112)
**107. Logs vs metrics vs traces?** Logs: detailed events (my JSON logs). Metrics: numbers over time (request rate, p95). Traces: one request across services (correlation id is a lightweight version).

**108. How do you detect an integration failure early?** Every call is logged with outcome; consecutive failures change health and auto-raise an incident; scheduled health checks; n8n alerts on patterns.

**109. Walk me through handling a SEV1 payment outage.** Confirm (distinguish declines from gateway errors), open/claim the incident, escalate, activate fallback (standalone terminals), communicate, monitor provider, verify recovery, reconcile stuck authorisations, write RCA. (Runbook RB-02.)

**110. What is a root-cause analysis?** Finding the underlying cause rather than the symptom — e.g. 5 Whys. The Simphony 422s were caused by a menu-change process gap, so the fix included a menu-sync check, not just mapping one item.

**111. MTTR vs MTTD?** Mean time to detect / to resolve. Automated alerts cut MTTD; runbooks and retry tooling cut MTTR. My incident report computes MTTR by severity.

**112. How do you prevent recurrence?** Add a test that reproduces it, add monitoring for its signal, fix the process, update the runbook, share in a review.

## T. AI-assisted development (113–116)
**113. How do you use AI coding tools?** For requirements drafts, boilerplate, test ideas, SQL, debugging hypotheses and documentation. I review everything, run tests, and own the result.

**114. Give an example where AI output was wrong.** Generated code can look right but miss context — e.g. assuming `EmailStr` would accept internal `.local` addresses, or that a migration runner can pass raw SQL through a parameterised call. Tests and a real Postgres run caught both. (See Doc 11.)

**115. How do you check AI-generated code for security issues?** Read it, run linters with security rules (ruff `S` rules flagged hashing and SQL-string patterns that I reviewed one by one), check secrets handling, authZ on every endpoint, input validation, and add negative tests.

**116. Would you paste company code or credentials into an AI tool?** Only within company policy and approved tools; never credentials or customer data.

## U. Behavioural (117–122) — answer with STAR, honestly
**117. Tell me about a project you delivered end to end.** TableFlow: I identified the problem space, wrote requirements, designed, built, tested on real Postgres, wrote runbooks. Be specific about what was simulated.

**118. Tell me about a bug you found and fixed.** The psycopg `%` placeholder issue in the migration runner — Situation (migration failed), Task (make migrations reliable), Action (read the traceback, isolated driver behaviour, executed raw SQL via DBAPI cursor, added a comment and test coverage), Result (migrations apply cleanly on Postgres; drift test in CI).

**119. Describe a trade-off you made.** In-process rate limiter and metrics: simple and testable, but not shared across replicas. I documented the upgrade path rather than adding Redis now.

**120. How do you explain technical issues to non-technical people?** Impact first ("Uber orders at Sandton aren't reaching the kitchen"), what we're doing, the workaround, next update time — no jargon.

**121. When did you have to learn something quickly?** Reading vendor-style API concepts (Simphony checks, ISO 8583 codes, Snowflake key-pair) and turning them into working adapters and tests.

**122. Why this role?** It combines what the project practises: talking to Finance and Operations, building integrations and internal tools in Python/React/Postgres/n8n, testing and releasing — in a restaurant business where the impact is visible every trading day.
