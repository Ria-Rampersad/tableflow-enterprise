# 04 · Process Maps, System Architecture, Integration Architecture & Data Flows

All diagrams are Mermaid (render on GitHub, in VS Code with a Mermaid extension, or at mermaid.live).

## 1. Current-state process (before TableFlow)

```mermaid
flowchart LR
  C[Customer orders on Uber Eats / Mr D] --> T[Provider tablet at branch]
  T -->|cashier re-keys 2-4 min| POS[(Simphony POS)]
  POS --> K[Kitchen]
  CARD[Card payment] --> TJ[(Payment switch)]
  TJ -->|T+1 CSV by email| FIN[Finance Excel]
  POS -->|manual export| FIN
  FIN -->|2-4 days later| D{Discrepancy?}
  D -->|yes| PH[Phone calls to branches]
  X[Integration failure] -.->|nobody alerted| BM[Branch manager phones Head Office]
```

## 2. Future-state process (with TableFlow)

```mermaid
flowchart LR
  C[Customer] --> P[Uber Eats / Mr D]
  P -->|REST + API key| TF[TableFlow API]
  TF -->|validate, de-dupe, store| DB[(PostgreSQL)]
  TF -->|create check, retry| POS[(Simphony - simulated)]
  POS --> K[Kitchen]
  TF -->|authorise, idempotent| PAY[(Payment gateway - simulated)]
  PAY -->|signed webhook| TF
  TF -->|earn points| LOY[(Loyalty - simulated)]
  TF -->|outbox events| N8N[n8n workflows]
  N8N -->|alerts| CH[Slack / Teams / alert sink]
  N8N -->|06:00 reconcile| TF
  DB -->|ELT| SF[(Snowflake / DuckDB demo)]
  TF --> UI[React dashboard]
```

## 3. System architecture

```mermaid
flowchart TB
  subgraph Client
    B[Browser - React + TypeScript SPA]
  end
  subgraph Edge
    NG[nginx :8080 - static SPA + reverse proxy /api]
  end
  subgraph App[FastAPI :8000]
    MW[Middleware: correlation ID, metrics, CORS, error envelope]
    R[Routers /api/v1/*]
    SEC[security: JWT, OAuth2, RBAC, API keys, HMAC, key-pair]
    SVC[services: orders, payments, loyalty, reconciliation, incidents, reporting, automation, pos]
    WH[webhooks.processor]
    INT[integrations: IntegrationRunner + adapters]
    OB[notifications outbox + async dispatcher]
  end
  PG[(PostgreSQL 16)]
  N8N[n8n]
  SF[(Snowflake)]
  V[Vendor systems - simulated]
  B --> NG --> MW --> R --> SEC
  R --> SVC --> INT --> V
  R --> WH --> SVC
  SVC --> PG
  SVC --> OB -->|HTTP POST| N8N
  N8N -->|OAuth2 client credentials| R
  PG -->|extract_load.py| SF
```

| Component | Responsibility | Tech |
|---|---|---|
| React SPA | 17 screens (incl. login), charts, forms, validation, error/loading states | React 18, TypeScript, Vite, Recharts |
| nginx | Serves SPA, proxies API (single origin), security headers | nginx 1.27 |
| FastAPI | REST API, validation, auth, business logic | Python 3.12+, FastAPI, Pydantic v2 |
| IntegrationRunner | Retries, logging, health, auto-incidents for every vendor call | `integrations/base.py` |
| Adapters | Map TableFlow ↔ vendor formats (simulated transport) | `integrations/*.py` |
| Webhook processor | Verify, de-dupe, process, replay | `webhooks/processor.py` |
| Outbox | Reliable, non-blocking notifications to n8n | `services/notifications.py` |
| PostgreSQL | System of record, constraints, triggers, views | PostgreSQL 16, SQL migrations |
| n8n | 8 workflows: alerts, retries, scheduled reconciliation & reports | n8n 1.x |
| Snowflake | Analytical warehouse (RAW → STAGING → ANALYTICS) | SQL + Python ELT |

## 4. Integration architecture

```mermaid
flowchart LR
  subgraph Inbound
    UE[Uber Eats] -->|POST /partners/uber-eats/orders\nX-API-Key, rate-limited| A1[UberEatsAdapter.to_canonical]
    MD[Mr D] -->|POST /partners/mr-d/orders| A2[MrDAdapter.to_canonical]
    TJW[Gateway webhooks] -->|X-TJ-Signature t,v1| WP[Webhook processor]
    UW[Uber webhooks] -->|X-Uber-Signature| WP
    MW[Mr D webhooks] -->|X-MrD-Signature| WP
  end
  A1 --> CO[CanonicalOrder]
  A2 --> CO
  CO --> OS[orders.ingest]
  subgraph Outbound via IntegrationRunner
    OS --> SIM[MicrosSimphonyAdapter]
    PS[payments.create_payment] --> TJ[TransactionJunctionAdapter]
    LS[loyalty.earn/redeem] --> LP[LoyaltyAdapter]
    AU[automation] --> GL[FinanceSystemAdapter]
    AU --> BO[BackOfficeAdapter]
    OS --> PUSH[Provider status push]
  end
```

Pattern summary: **canonical data model** (one internal order shape), **adapter** per vendor, **single choke
point** for outbound calls (retry/log/health), **idempotency** at every inbound edge (orders, payments, webhooks),
**transactional outbox** for notifications.

## 5. End-to-end data flow — digital order (the 10 steps)

```mermaid
sequenceDiagram
  autonumber
  participant Cust as Customer
  participant UE as Uber Eats
  participant API as TableFlow API
  participant DB as PostgreSQL
  participant POS as Simphony adapter
  participant PAY as Payment adapter
  participant LOY as Loyalty adapter
  participant N8N as n8n
  participant SF as Snowflake
  Cust->>UE: places order
  UE->>API: POST /partners/uber-eats/orders (X-API-Key)
  API->>API: rate limit, API key, map to CanonicalOrder, validate rules
  API->>DB: INSERT order + items + audit + outbox(new_order)
  API-->>UE: 202 Accepted {order_number}
  API->>POS: create_check (background task, up to 3 attempts)
  POS-->>API: checkRef -> order.status = accepted
  API->>PAY: authorise (Idempotency-Key)
  PAY-->>API: 00 Approved -> payment.status = authorised
  PAY->>API: webhook payment.captured (HMAC signed)
  API->>DB: verify, de-dupe, payment.status = captured
  API->>LOY: post earn (1 pt / R10)
  API->>N8N: outbox dispatcher POSTs events
  N8N->>N8N: classify, alert, retry, escalate
  DB->>SF: nightly extract_load.py (ELT)
```

Step-by-step:
1. **Customer places a digital order** in the Uber Eats app.
2. **Provider sends an API request** to `/api/v1/partners/uber-eats/orders` with its API key; the sliding-window rate limiter and `require_partner_key` run first.
3. **Backend validates**: Pydantic parses the body; `UberEatsAdapter.to_canonical` maps cents→Rand and provider fields → `CanonicalOrder`; `orders.ingest` applies BR-ORD-01..05.
4. **Order stored in PostgreSQL** inside one transaction with its items, the customer upsert, an `audit_logs` row and a `notifications` outbox row. Response **202** is returned immediately.
5. **Forwarded to the POS adapter** in a FastAPI background task: `forward_to_pos` → `IntegrationRunner.call` → `MicrosSimphonyAdapter.create_check`. Success sets `pos_check_ref` and `accepted`; failure after retries sets `failed` and queues a `pos_failure` alert.
6. **Payment processed** through `POST /payments` with an `Idempotency-Key`; `TransactionJunctionAdapter.authorise` returns an ISO 8583-style response code.
7. **Webhook confirms payment**: the gateway (simulated) posts `payment.captured` signed with HMAC-SHA256 + timestamp; the processor verifies, de-duplicates, and sets `captured`.
8. **Loyalty points updated** inside the same handler: `loyalty.earn_for_order` writes the local ledger first, then posts to the platform; failure is kept as `failed` for retry.
9. **n8n triggers notifications**: the outbox dispatcher (async loop) POSTs pending rows to n8n webhook paths; workflows decide who to alert and may call back into the API.
10. **Analytics**: `snowflake/etl/extract_load.py` extracts incrementally (watermark on `updated_at`) and loads Snowflake RAW, then SQL builds STAGING and ANALYTICS marts.

## 6. Data flow diagram (level 1)

```mermaid
flowchart LR
  E1([Ordering providers]) -->|orders, cancellations| P1((1. Ingest orders))
  P1 --> D1[(orders / order_items / customers)]
  P1 -->|check| E2([POS])
  E3([Payment gateway]) -->|auth result, webhooks| P2((2. Process payments))
  P2 --> D2[(payments / refunds / webhook_events)]
  P2 --> P3((3. Loyalty))
  P3 --> D3[(loyalty_accounts / loyalty_transactions)]
  P3 --> E4([Loyalty platform])
  E2 -->|closed checks| P4((4. Reconcile))
  E3 -->|settlement CSV| P4
  D1 --> P4
  D2 --> P4
  P4 --> D4[(reconciliation_runs / records)]
  P5((5. Monitor & alert)) --> D5[(integration_logs / incidents / notifications)]
  D5 --> E5([n8n -> people])
  D1 & D2 & D3 --> P6((6. ELT)) --> E6([Snowflake])
  ALL[every process] --> D6[(audit_logs)]
```

## 7. Deployment view

```mermaid
flowchart LR
  dev[Developer laptop] -->|git push| GH[GitHub]
  GH --> CI[GitHub Actions: lint, tests SQLite+Postgres, build, docker, Newman, n8n runner]
  CI -->|images| REG[(Container registry - not configured)]
  subgraph docker-compose
    fe[frontend nginx :8080] --> be[backend :8000]
    be --> pg[(postgres :5432)]
    n8n[n8n :5678] --> be
    be --> n8n
  end
```
