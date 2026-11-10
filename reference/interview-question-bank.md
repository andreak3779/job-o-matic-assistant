# Interview Question Bank — Full Stack .NET Developer
**Last researched:** October 19, 2026 · **Role:** Full Stack .NET Developer (ASP.NET Core / C# / SQL Server / Angular or React / Azure)

Loaded by `interview_practice` (Step 2) and `interview_practice_job_description` (Step 4). Pick questions from here; never read the whole file aloud to the user — the "Look for" notes are the **assessor's key**, and showing them before the user answers defeats the practice.

This bank is deliberately **role-generic**. It contains no facts about the candidate. Evidence, gaps and cert status come live from the profile at run time, so nothing here goes stale when the profile regenerates.

## How to use an entry

`- **ID [level]** Question — *Look for:* what a strong answer must cover · *Red flag:* what loses credibility`

| Level | Meaning | Typical use |
|---|---|---|
| `[J]` | Fundamentals — any full-stack .NET hire must answer cleanly | Phone screen, warm-up |
| `[M]` | Working knowledge — expected at 3–6 years | Technical screen |
| `[S]` | Senior — trade-offs, scale, judgement | Senior roles, final round |

Each section header lists its **tags**. `interview_practice_job_description` matches JD skill terms to these tags to choose questions.

**Refreshing the bank:** if "Last researched" is more than ~6 months old, or the user asks to refresh it, re-run the web searches listed under *Sources* and update the entries — keep the IDs stable so session logs still point at the right questions.

---

## 1. C# and the .NET runtime
Tags: `csharp` `dotnet` `oop` `linq` `generics`

- **CS-01 [J]** What is the difference between value types and reference types? What is boxing and why does it matter? — *Look for:* value types copy their data, reference types copy the reference and can be null; boxing allocates a heap copy and can cause hidden GC pressure in hot paths; generics avoid it. *Red flag:* "value types live on the stack, reference types on the heap" stated as an absolute (struct fields inside a class live on the heap).
- **CS-02 [J]** When would you use a class, a struct, or a record? — *Look for:* records give value-based equality and `with` copying, suited to immutable data; classes for identity and mutable behaviour; structs for small, short-lived value semantics.
- **CS-03 [J]** Interface vs abstract class — when do you choose each? — *Look for:* interface = contract / multiple implementation; abstract class = shared state or behaviour with a base; default interface methods exist but are not a replacement for design; composition over inheritance.
- **CS-04 [M]** Explain LINQ deferred execution and the difference between `IEnumerable<T>` and `IQueryable<T>`. — *Look for:* query runs on enumeration, so re-enumerating re-runs it; `IQueryable` builds an expression tree translated to SQL by the provider, `IEnumerable` filters in memory. *Red flag:* calling `.ToList()` before `.Where()` on a database query.
- **CS-05 [M]** How do `IDisposable`, `using` and the garbage collector fit together? — *Look for:* GC reclaims memory, not unmanaged resources; `using`/`await using` guarantees `Dispose`; finalizers are a backstop; `IAsyncDisposable` for async cleanup.
- **CS-06 [M]** What problem do nullable reference types solve and how do you adopt them in an existing codebase? — *Look for:* compile-time warnings for possible null dereference; enable per project/file, fix warnings incrementally; they do not add runtime checks.
- **CS-07 [M]** What are delegates, events, `Func`/`Action`, and closures? What can go wrong with closures? — *Look for:* delegates are type-safe function references; closures capture variables, not values; event handlers that are never unsubscribed cause memory leaks.
- **CS-08 [M]** `==` vs `Equals` vs `ReferenceEquals`; what is the `GetHashCode` contract? — *Look for:* equal objects must have equal hash codes; override both together; mutable keys in a dictionary are a bug.
- **CS-09 [M]** What language/runtime features from recent C#/.NET releases have you actually used, and why? — *Look for:* concrete use (pattern matching, primary constructors, collection expressions, minimal hosting, records, nullable) with a reason, not a feature list. *Red flag:* naming features never used.
- **CS-10 [J]** `throw` vs `throw ex` — and when should you *not* catch an exception? — *Look for:* `throw;` preserves the stack trace; catch only where you can handle or add context; don't swallow; custom exceptions sparingly.
- **CS-11 [S]** How does .NET garbage collection work and how would you track down a memory leak? — *Look for:* generations 0/1/2 and the large object heap, server vs workstation GC; leaks are usually static references, event handlers, captured closures, unbounded caches; tools: `dotnet-counters`, `dotnet-dump`, memory profiler.
- **CS-12 [S]** When do `Span<T>`, `ValueTask` or pooling matter? — *Look for:* only on measured hot paths to cut allocations; premature use hurts readability; measure first (BenchmarkDotNet).

## 2. Async and concurrency
Tags: `async` `concurrency` `threading` `tasks`

- **AS-01 [J]** What does `async`/`await` actually do? Does it create a new thread? — *Look for:* it frees the thread during I/O and resumes on completion; a Task is a promise of a result, not a thread; this is why async scales a web server.
- **AS-02 [M]** Why are `async void`, `.Result` and `.Wait()` problems? — *Look for:* `async void` can't be awaited and its exceptions can crash the process (event handlers only); blocking on async causes thread-pool starvation under load, and deadlocks in contexts with a synchronization context; keep async all the way down. *Red flag:* "ConfigureAwait(false) everywhere" with no idea why it matters less in ASP.NET Core.
- **AS-03 [M]** How do you run several independent calls concurrently, and how do you handle failure and cancellation? — *Look for:* `Task.WhenAll`, what happens to exceptions (first thrown, others on the tasks), `CancellationToken` passed through, timeouts, no `Task.Run` around I/O in a web request.
- **AS-04 [M]** CPU-bound vs I/O-bound work in a web app — how do you handle each? — *Look for:* I/O → async APIs; CPU-bound → offload to a background worker/queue rather than `Task.Run` on the request path; `Parallel.ForEachAsync` for bounded fan-out.
- **AS-05 [M]** Show me a race condition and how you'd fix it. — *Look for:* shared mutable state; `lock` can't contain `await`, use `SemaphoreSlim`; `ConcurrentDictionary`, `Interlocked`; or remove shared state entirely.
- **AS-06 [S]** Your API throws timeouts under load but CPU is low. What do you suspect? — *Look for:* thread-pool starvation from sync-over-async, connection pool exhaustion, `HttpClient` misuse, slow downstream; diagnose with counters/traces before changing code.
- **AS-07 [S]** How would you build a reliable background worker? — *Look for:* `BackgroundService` with a DI scope per unit of work, graceful shutdown via the stopping token, a durable queue for work that must survive restarts, idempotent handlers.

## 3. ASP.NET Core
Tags: `aspnet-core` `mvc` `razor` `blazor` `minimal-api` `middleware` `di` `web-forms`

- **AP-01 [J]** Walk me through the ASP.NET Core request pipeline. — *Look for:* middleware runs in registration order and can pass on or short-circuit; exception handling first, then HTTPS/static files, routing, CORS, authentication before authorization, then endpoints. *Red flag:* wrong auth/authorization order.
- **AP-02 [J]** Explain the three DI lifetimes with an example of each. — *Look for:* transient = new per injection; scoped = one per request; singleton = one per app; DbContext is scoped.
- **AP-03 [M]** What is a captive dependency and how do you avoid it? — *Look for:* a singleton holding a scoped service (e.g. DbContext) keeps one instance forever; use `IServiceScopeFactory`/a factory per unit of work; scope validation in development catches it.
- **AP-04 [M]** Middleware vs filters vs endpoint filters — how do you choose? — *Look for:* middleware sees every request with only `HttpContext`; MVC filters run inside MVC with action context (model state, results); endpoint filters for minimal APIs.
- **AP-05 [M]** Controllers vs minimal APIs vs Razor Pages vs Blazor — how do you choose? — *Look for:* same runtime; choose by team, size and structure; minimal APIs have less ceremony but need deliberate organisation; Blazor/Razor for server-rendered UI.
- **AP-06 [M]** How do you manage configuration and secrets across environments? — *Look for:* `appsettings` + environment overrides + env vars; options pattern with validation on start; user-secrets locally, Key Vault in the cloud; nothing secret in source control.
- **AP-07 [M]** How do you handle errors globally in an API? — *Look for:* exception-handling middleware/`IExceptionHandler`, consistent `ProblemDetails`, correct status codes, no stack traces in production, logging with a correlation id.
- **AP-08 [M]** How do you validate input and why use DTOs instead of entities? — *Look for:* data annotations/FluentValidation, `[ApiController]` automatic 400s; DTOs prevent over-posting and decouple the API contract from the schema.
- **AP-09 [M]** Why use `IHttpClientFactory`, and how do you add resilience? — *Look for:* avoids socket exhaustion and stale DNS, centralised config; retries with backoff, timeouts, circuit breaker via the resilience handler; retries only idempotent calls.
- **AP-10 [M]** What would you put in place so you can support this service in production? — *Look for:* structured logging, metrics, distributed tracing (OpenTelemetry/Application Insights), liveness vs readiness health checks, alerts.
- **AP-11 [S]** Caching strategy for an API — what do you use and what goes wrong? — *Look for:* `IMemoryCache` per node vs distributed cache (Redis) vs `HybridCache`/output caching; invalidation plan first; cache stampede protection; don't cache per-user data in a shared key.
- **AP-12 [S]** What changes when you scale the app to several instances? — *Look for:* stateless instances, shared data-protection keys, distributed cache/session, sticky sessions avoided, SignalR needs a backplane, forwarded headers behind a proxy.
- **AP-13 [M]** Blazor Server vs WebAssembly vs the newer render modes — trade-offs? — *Look for:* latency and connection per user vs download size and offline; SEO/first-load; JS interop; choose per feature.
- **AP-14 [M]** CORS and rate limiting — what are they for and where do they go in the pipeline? — *Look for:* CORS is browser-enforced, not security against non-browser clients; rate limiting protects availability; CORS before auth so preflight works.
- **AP-15 [M]** What is your approach to a legacy ASP.NET Web Forms / .NET Framework app you must keep running while modernising? — *Look for:* strangler approach, upgrade assistant tooling, shared libraries targeting .NET Standard, keep deploys safe, incremental. (See also AR-08.)

## 4. Web API and REST design
Tags: `rest` `api` `webapi` `odata` `openapi` `graphql` `grpc`

- **API-01 [J]** What makes an API RESTful? Which status codes do you use for create, update, delete, validation and conflict? — *Look for:* resources and verbs, statelessness; 201 + Location, 200/204, 400/422, 404, 409; idempotency of GET/PUT/DELETE.
- **API-02 [M]** PUT vs PATCH vs POST — and how do you make a POST safe to retry? — *Look for:* PUT replaces, PATCH partially updates, POST creates/acts; idempotency keys stored atomically with the operation.
- **API-03 [M]** How do you version an API, and what counts as a breaking change? — *Look for:* URL/header/query strategies; additive changes are safe; deprecation policy and communication to consumers.
- **API-04 [M]** Design pagination, filtering and sorting for a large list endpoint. — *Look for:* offset vs cursor (keyset) trade-offs, max page size, stable sort, total counts cost, indexes behind the filters.
- **API-05 [M]** REST vs GraphQL vs gRPC — when would you pick each? — *Look for:* REST for public/browser clients, GraphQL for flexible client-driven queries (over/under-fetching) with cost control, gRPC for internal high-throughput contracts.
- **API-06 [M]** How do you document and keep an API contract trustworthy? — *Look for:* OpenAPI generated from code or contract-first, client generation, contract tests, changelog.
- **API-07 [S]** How would you expose a long-running operation? — *Look for:* 202 Accepted + status endpoint or webhook; idempotent start; polling vs push; timeouts and retries.
- **API-08 [M]** What are the benefits and risks of exposing OData or a generic query API? — *Look for:* flexibility for clients vs unbounded/expensive queries; enforce page size, allowed properties, query-cost limits; consider purpose-built endpoints.

## 5. Authentication, authorization and security
Tags: `security` `auth` `jwt` `oauth` `oidc` `identity` `owasp`

- **SE-01 [J]** Authentication vs authorization — and where do they sit in the pipeline? — *Look for:* identity vs access; authentication first.
- **SE-02 [M]** How does JWT authentication work, and what must the server validate? — *Look for:* signed bearer token; validate signature, issuer, audience, expiry, key rotation; stateless; revocation is the hard part → short lifetimes + refresh tokens with rotation.
- **SE-03 [M]** Where should an Angular/React SPA store tokens? — *Look for:* trade-offs between `httpOnly` cookie (CSRF considerations) and in-memory/localStorage (XSS exposure); backend-for-frontend pattern; never claim one is "perfectly safe".
- **SE-04 [M]** Explain OAuth 2.0 / OpenID Connect flows you'd use for a SPA and for service-to-service calls. — *Look for:* authorization code + PKCE for SPAs; client credentials for services; implicit flow is obsolete; OIDC adds identity.
- **SE-05 [M]** How do you implement role- and policy-based authorization? — *Look for:* claims, `[Authorize]` with policies and requirements, resource-based checks, server-side always (client checks are UX only).
- **SE-06 [M]** Walk through the OWASP Top 10 risks that matter most for a .NET + SPA app and how you mitigate them. — *Look for:* injection → parameterised queries; XSS → output encoding/CSP, framework escaping; broken access control; CSRF/antiforgery; misconfiguration; vulnerable dependencies; logging.
- **SE-07 [M]** How do you manage secrets and cloud identity? — *Look for:* Key Vault, managed identity instead of connection-string passwords, least privilege, rotation.
- **SE-08 [S]** Threat-model a login endpoint. — *Look for:* credential stuffing, lockout/rate limiting, MFA, password hashing with a slow salted algorithm (ASP.NET Core Identity), generic error messages, audit logging.
- **SE-09 [M]** How do you think about security in cloud applications? — *Look for:* least privilege and managed identities, secrets in a vault, network isolation/private endpoints, TLS everywhere, patching dependencies and images, logging/alerting on suspicious activity, shared-responsibility awareness.

## 6. Entity Framework Core and data access
Tags: `ef-core` `entity-framework` `orm` `data-access` `dapper` `ado-net`

- **EF-01 [J]** What are DbContext, DbSet, the change tracker and migrations? — *Look for:* unit of work + repository-like sets; snapshot change tracking; `SaveChanges` generates SQL for changes; migrations version the schema.
- **EF-02 [M]** What lifetime should a DbContext have, and how do you use it in a background service? — *Look for:* scoped; not thread-safe; never a singleton; create a scope or use `IDbContextFactory`.
- **EF-03 [M]** Tracking vs `AsNoTracking`, and when do you use projections? — *Look for:* read-only queries skip tracking; `Select` into DTOs fetches only needed columns; tracked entities needed only when saving.
- **EF-04 [M]** What is the N+1 problem, how do you detect it and fix it? — *Look for:* one query per parent for children; fix with `Include`, projection, or split queries; detect with query logging/`ToQueryString`; mention cartesian explosion with multiple collection includes.
- **EF-05 [M]** Eager, lazy and explicit loading — trade-offs? — *Look for:* lazy loading is off by default and hides queries; prefer explicit eager loading or projections.
- **EF-06 [M]** How do you apply migrations safely in production? — *Look for:* generate idempotent scripts or migration profiles in the pipeline, not `Database.Migrate()` at startup; backwards-compatible (expand/contract) changes; rollback plan.
- **EF-07 [M]** How do you handle two users editing the same record? — *Look for:* optimistic concurrency with a row-version token, `DbUpdateConcurrencyException` handling (reload and merge/ask), pessimistic locks only when conflicts are frequent.
- **EF-08 [M]** How do transactions work in EF Core? — *Look for:* one `SaveChanges` is atomic; explicit transaction for several saves; connection resiliency/execution strategies interact with manual transactions.
- **EF-09 [M]** EF Core vs Dapper vs stored procedures — how do you choose? — *Look for:* EF for productivity and change tracking, Dapper/raw SQL for hot read paths or complex SQL, stored procs where the DB team owns logic; mixing is fine.
- **EF-10 [S]** `ExecuteUpdate`/`ExecuteDelete` and global query filters — what do they bypass or affect? — *Look for:* bulk operations skip the change tracker, interceptors and audit logic; query filters power soft delete/multi-tenancy but can surprise (`IgnoreQueryFilters`).
- **EF-11 [S]** A query that should be fast is slow. Walk through your diagnosis. — *Look for:* capture the generated SQL, check the execution plan, indexes and statistics, row counts, tracking, round trips; change one thing and re-measure.
- **EF-12 [M]** Code-first vs database-first, and how do you model value objects and enums? — *Look for:* owned types, value converters, configuration via `IEntityTypeConfiguration`; database-first/scaffolding for existing schemas.

## 7. SQL Server and relational databases
Tags: `sql-server` `tsql` `database` `ssis` `sql` `postgresql` `oracle`

> Section written from standard SQL Server practice rather than the web sources (which did not cover it).

- **SQ-01 [J]** Clustered vs non-clustered index; what is a covering index and when do indexes hurt? — *Look for:* clustered defines row order (one per table); non-clustered separate structure; covering via `INCLUDE`; extra write cost and storage.
- **SQ-02 [M]** How do you read an execution plan and find the problem? — *Look for:* scans vs seeks, key lookups, estimated vs actual rows (statistics), missing-index hints with caution, expensive operators.
- **SQ-03 [M]** Explain ACID, isolation levels, and how you would diagnose and prevent a deadlock. — *Look for:* read committed vs snapshot/RCSI vs serializable trade-offs; consistent access order, short transactions, proper indexes; deadlock graphs.
- **SQ-04 [M]** Stored procedures vs inline/ORM SQL — pros and cons? And what is parameter sniffing? — *Look for:* plan reuse, permissions, version control and testing difficulty; parameterised always; sniffing = plan compiled for atypical parameters, mitigations (recompile, OPTIMIZE FOR, plan guides).
- **SQ-05 [M]** Joins, CTEs, window functions, temp tables vs table variables — when do you use each? — *Look for:* correct join semantics, `ROW_NUMBER`/`LAG`, recursive CTE for hierarchies, temp tables for larger intermediate sets.
- **SQ-06 [M]** How do you design a schema for a new feature — normalisation vs denormalisation? — *Look for:* 3NF as default, keys and constraints enforcing integrity, denormalise deliberately for read performance, audit columns.
- **SQ-07 [S]** Walk me through optimising a slow report/query end to end. — *Look for:* baseline measurement, plan, indexing, set-based rewrite over cursors/loops, avoiding functions on indexed columns, verify improvement with numbers.
- **SQ-08 [M]** SQL vs NoSQL (document, key-value, cache) — how do you decide? — *Look for:* relational for integrity and ad-hoc queries; document/key-value for scale or flexible shape; polyglot persistence has an operational cost.
- **SQ-09 [M]** How do you change a production schema with no downtime? — *Look for:* additive first, backfill, dual-write/read, then remove; online index operations; staging rehearsal.
- **SQ-10 [M]** When would you use SSIS or another ETL tool vs code? — *Look for:* bulk, scheduled, data-heavy transforms and repeatable packages vs application logic; logging, restartability, performance tuning.

## 8. Front-end: Angular, React, TypeScript, Blazor
Tags: `angular` `react` `typescript` `javascript` `blazor` `css` `html` `frontend` `rxjs` `ngrx`

- **FE-01 [J]** Client-side rendering vs server-side rendering vs SSR with hydration — trade-offs? — *Look for:* first paint, SEO, complexity, caching, server cost.
- **FE-02 [J]** Explain closures, `==` vs `===`, the event loop, and promises vs `async/await`. — *Look for:* correct mental model of the call stack/microtasks; error handling in async code.
- **FE-03 [M]** TypeScript: `type` vs `interface`, `unknown` vs `any`, generics, strict mode. — *Look for:* use of `strict`, avoiding `any`, narrowing, utility types.
- **FE-04 [M]** (Angular) Explain change detection, `OnPush` and signals. — *Look for:* default checks the whole tree on events; `OnPush` checks on input change/event/markForCheck; signals give fine-grained reactivity.
- **FE-05 [M]** (Angular) RxJS: Observable vs Promise; `switchMap` vs `mergeMap`; avoiding subscription leaks. — *Look for:* lazy, cancellable, multi-value; `switchMap` cancels the previous (search-as-you-type), `mergeMap` runs concurrently; `async` pipe, `takeUntilDestroyed`.
- **FE-06 [M]** (Angular) Services and DI, lazy-loaded routes, guards, and HTTP interceptors — how do you use them? — *Look for:* interceptor to attach tokens and handle 401; guards are UX not security; standalone components vs modules.
- **FE-07 [M]** How do you manage state in a front-end app, and when is NgRx/Redux overkill? — *Look for:* local state first, services/signals for shared state, store for complex cross-cutting state with effects and devtools; cost of boilerplate.
- **FE-08 [M]** (React) `useState`/`useEffect`, keys, memoisation, controlled vs uncontrolled inputs. — *Look for:* effect cleanup and dependency array correctness, stable keys, `memo`/`useCallback` only when measured.
- **FE-09 [M]** Forms and validation: reactive vs template-driven; client vs server validation. — *Look for:* client validation is UX, server validation is authoritative; surface server errors.
- **FE-10 [M]** A page loads slowly. How do you diagnose and improve it? — *Look for:* DevTools/Lighthouse, profile analysis, lazy loading, image/caching, `trackBy`/virtual scroll, Core Web Vitals, API latency.
- **FE-11 [M]** What accessibility basics do you build in? — *Look for:* semantic HTML, labels, keyboard navigation, focus management, ARIA only when needed, contrast.
- **FE-12 [J]** Flexbox vs CSS Grid; how do you make a layout responsive? — *Look for:* 1-D vs 2-D layout, media queries/relative units, mobile first.
- **FE-13 [M]** How does the front end handle API errors, loading states and token expiry? — *Look for:* central error handling, retry/refresh flow, user-visible states, no silent failures, safe rendering (no `innerHTML` with untrusted data).
- **FE-14 [S]** How would you structure a large front-end codebase for several teams? — *Look for:* feature boundaries, shared library, monorepo tooling, lint/format rules, versioned design system, testing strategy.
- **FE-15 [M]** (Blazor) When would you use JS interop and what are the pitfalls? — *Look for:* only for browser APIs without a .NET equivalent; async calls, disposal, avoid chatty calls.

## 9. Testing
Tags: `testing` `tdd` `xunit` `nunit` `moq` `e2e` `cypress` `playwright` `unit-testing`

- **TE-01 [J]** Unit vs integration vs end-to-end tests — what is the test pyramid for? — *Look for:* many fast unit tests, fewer integration, few E2E; cost vs confidence.
- **TE-02 [M]** What is TDD, and when does it help or get in the way? — *Look for:* red-green-refactor; helps on logic-heavy code and legacy fixes; pragmatic about UI and exploratory work.
- **TE-03 [M]** How do you use mocks, and when should you *not* mock? — *Look for:* mock external boundaries (HTTP, clock, email), not your own domain logic; verify behaviour not implementation; fakes vs mocks vs stubs vocabulary.
- **TE-04 [M]** How do you integration-test an ASP.NET Core API? — *Look for:* `WebApplicationFactory`, real database engine (Testcontainers/SQL Server/SQLite caveats) over the in-memory provider, seeded data, auth handled in test host.
- **TE-05 [M]** How do you test front-end code? — *Look for:* component tests (Jasmine/Jest/Testing Library), service tests with `HttpTestingController`, Cypress/Playwright for critical journeys; avoid brittle selectors.
- **TE-06 [M]** What makes a test flaky, and what does code coverage actually tell you? — *Look for:* time, ordering, shared state, async waits; coverage shows what's *not* tested, not quality; coverage gates as a guardrail.
- **TE-07 [S]** You inherit untested legacy code that must change. What do you do first? — *Look for:* characterization tests, find seams, small safe refactors, don't rewrite blind.
- **TE-08 [M]** How do you make sure your code is reliable before it ships, and how do you think about code quality day to day? — *Look for:* tests at the right layers, code review, static analysis/linting, CI gates, small increments, following team standards; speaks about decisions and trade-offs rather than tactics only; knows when to raise a concern vs follow the team's approach.

## 10. Architecture and design
Tags: `architecture` `solid` `clean-architecture` `ddd` `cqrs` `microservices` `messaging` `legacy` `design-patterns`

- **AR-01 [J]** Explain SOLID with an example from real code. — *Look for:* real example, not definitions; honest about where you bent a rule.
- **AR-02 [M]** Which design patterns do you actually use? Is the Repository pattern still needed on top of EF Core? — *Look for:* Strategy, Factory, Decorator, Adapter in context; EF already is a unit of work/repository — wrap only when it earns its keep (testing seam, domain boundary).
- **AR-03 [M]** Describe Clean/Onion architecture or vertical slices and the dependency rule. — *Look for:* domain at the centre with no outward dependencies, infrastructure at the edge; pragmatism over ceremony.
- **AR-04 [S]** Monolith vs modular monolith vs microservices — how do you decide? — *Look for:* team size, independent scaling and deployment needs, operational cost; microservices are not the default.
- **AR-05 [S]** When are CQRS or event sourcing justified? — *Look for:* only when read/write models diverge in shape or scale; adds eventual consistency and complexity.
- **AR-06 [S]** Explain queues vs topics, at-least-once delivery, idempotency, dead-letter queues, and the outbox pattern. — *Look for:* handlers must be idempotent; poison messages go to DLQ; outbox solves "write DB and publish" atomically.
- **AR-07 [S]** How do you build resilience between services? — *Look for:* timeouts, retries with backoff and jitter, circuit breaker, bulkheads, fallbacks, sagas for multi-step consistency.
- **AR-08 [M]** How do you modernise a legacy application safely? (Follow-up: what is the hardest part of migrating from old to new technology?) — *Look for:* strangler-fig/incremental migration, characterization tests first, keep releasing, measure risk, data migration plan, rollback; hardest parts are usually undocumented behaviour, data, and people/process, not syntax.
- **AR-09 [M]** How do you decide whether to refactor or leave code alone? (Alt: what is your approach to technical debt?) — *Look for:* business value, risk, test safety net, boy-scout rule, make debt visible.
- **AR-10 [M]** How do you document decisions and architecture? — *Look for:* ADRs, diagrams as code/lightweight, READMEs that run, docs close to code.

## 11. Cloud (Azure), containers and DevOps
Tags: `azure` `docker` `kubernetes` `ci-cd` `devops` `github-actions` `iac` `terraform` `bicep` `linux`

- **CL-01 [J]** What is CI/CD and what stages are in your ideal pipeline? — *Look for:* build, test, static analysis, package, deploy to environments with approvals, rollback; trunk-based or short-lived branches.
- **CL-02 [M]** Explain Docker image vs container, multi-stage builds, and how you handle config and health checks. — *Look for:* small final images, config via environment variables, healthchecks gating startup, Compose for local multi-service setups.
- **CL-03 [M]** What are pods, deployments, services and probes in Kubernetes, and when is Kubernetes the wrong choice? — *Look for:* basic object model, liveness vs readiness; smaller teams are often better served by App Service/Container Apps.
- **CL-04 [M]** App Service vs Functions vs Container Apps vs AKS — how do you choose? — *Look for:* operational overhead, scaling model, event-driven vs always-on, cost.
- **CL-05 [M]** When would you use Blob/Queue Storage, Service Bus, Event Grid or Cosmos DB? — *Look for:* queues/topics for commands and reliable delivery, Event Grid for reactive event notification, Cosmos for global scale/partitioned documents, partition key choice.
- **CL-06 [M]** How do you monitor an application in Azure? — *Look for:* Application Insights/Log Analytics, KQL, alerts on symptoms, dashboards, distributed traces.
- **CL-07 [M]** How do you deploy with minimal risk? — *Look for:* slots/blue-green/canary, feature flags, database changes compatible with both versions, quick rollback.
- **CL-08 [S]** Why infrastructure-as-code, and Bicep vs Terraform? — *Look for:* repeatability, review, drift; state handling in Terraform; Azure-native vs multi-cloud.
- **CL-09 [M]** Git workflow: branching, pull requests, merge vs rebase, resolving conflicts. — *Look for:* small PRs, review culture, protect main, rebase local work / merge shared.
- **CL-10 [S]** How do you balance cost, scalability and reliability in a design? — *Look for:* explicit trade-offs, autoscaling limits, SLOs, avoiding over-engineering.
- **CL-11 [M]** Which Azure services have you used and how did you choose them? — *Look for:* real services matched to a real need with the alternative considered and rejected; honest about which were production vs lab/course exposure; no service-name dropping.
- **CL-12 [M]** How do you approach cost optimisation in Azure? — *Look for:* right-sizing and autoscale, consumption/serverless where traffic is spiky, reserved capacity for steady load, cost analysis and budgets/alerts, turning off idle environments, data transfer and logging costs, tagging for accountability.

## 12. Debugging, performance and production support
Tags: `performance` `debugging` `production-support` `observability` `code-review`

- **PR-01 [M]** An API endpoint is slow in production. Walk me through finding the cause. — *Look for:* measure first (traces/logs), isolate layer (client, API, DB, downstream), hypothesis, fix, verify with numbers.
- **PR-02 [M]** A bug only reproduces in production. What do you do? — *Look for:* logs/correlation ids, compare config/data, reproduce safely, feature flag/rollback, no testing in prod blindly.
- **PR-03 [S]** A .NET service shows rising memory or CPU. Which tools and steps? — *Look for:* `dotnet-counters`, `dotnet-trace`, `dotnet-dump`, profilers; GC metrics; isolate recent change.
- **PR-04 [M]** What do you look for in a code review? — *Look for:* correctness, tests, readability, security, performance only where relevant, kindness; small PRs.
- **PR-05 [S]** How do you run an incident and write a post-mortem? — *Look for:* restore service first, communicate, blameless review, concrete follow-ups.
- **PR-06 [M]** How do you provide on-call/production support while still delivering project work? — *Look for:* triage by impact, runbooks, protecting focus time, root cause vs workaround.
- **PR-07 [M]** Tell me about debugging a cloud application — where do you look first? — *Look for:* start from symptoms in logs/metrics/traces (Application Insights/Log Analytics, correlation ids), recent deployments and config changes, dependency health and throttling, then reproduce; isolate layer before changing code.

## 13. Behavioural and collaboration (STAR)
Tags: `behavioural` `communication` `teamwork` `leadership` `agile`

For every `BE-` question the answer is assessed with the **behavioural (STAR) rubric** in `interview-practice-rubric.md`. Model answers come from `star-bank.md`, never invented.

- **BE-01 [J]** Walk me through your background. — *Look for:* ~2 minutes, past → present → why this role, relevant highlights, no life story.
- **BE-02 [J]** Why this role and this company? — *Look for:* two specific, researched reasons; not generic flattery.
- **BE-03 [J]** Where do you want to be in a few years? — *Look for:* realistic growth aligned with the role.
- **BE-04 [J]** Tell me about a technical achievement you are proud of. — *Look for:* clear problem, personal contribution ("I"), measurable result.
- **BE-05 [J]** Describe an occasion when you failed at a task. What did you learn from it? — *Look for:* a failure that was genuinely learned from (not blame-shifting or a disguised strength); the gap named honestly (knowledge, process, estimation, support); how they responded and iterated; a concrete change in how they work now.
- **BE-06 [M]** Describe a disagreement with a teammate or lead about a technical approach. (Alt: tell me about working with someone whose perspective differed from yours.) — *Look for:* listening, evidence, compromise or commit; relationship preserved.
- **BE-07 [M]** Tell me about learning a new technology quickly under a deadline. — *Look for:* learning method, delivery, what was left unlearned.
- **BE-08 [M]** How do you explain a technical issue to a non-technical stakeholder? — *Look for:* outcome-first, analogies, no jargon, check for understanding.
- **BE-09 [M]** How do you prioritise when several projects have competing deadlines? (Alt: describe an occasion when you had to manage your time to complete a task.) — *Look for:* impact/urgency, communicating trade-offs, saying no; a named prioritisation method; stakeholders told about scope/timeline trade-offs; works smarter, not just harder.
- **BE-10 [M]** Tell me about taking over a codebase someone else wrote. — *Look for:* reading before changing, tests, asking questions, respect for prior decisions.
- **BE-11 [M]** What do you do with vague or changing requirements? — *Look for:* clarify, small increments, assumptions written down, early feedback.
- **BE-12 [S]** Tell me about improving a process or raising quality on your team. (Alt: tell me about a time you improved a process.) — *Look for:* identified a real problem, brought others along, measurable outcome.
- **BE-13 [M]** How do you respond to critical feedback? Give an example. — *Look for:* specific feedback, action taken, result.
- **BE-14 [S]** When do you raise a concern vs go with the team's approach? — *Look for:* risk-based judgement, disagree-and-commit, evidence not opinion.
- **BE-15 [M]** How do you use AI coding assistants responsibly? — *Look for:* review everything, tests as the safety net, security/IP awareness, uses it to learn and speed up, not as an oracle.
- **BE-16 [J]** What are your strengths and your weaknesses? — *Look for:* honest and specific, with a concrete mitigation.
- **BE-17 [J]** What questions do you have for us? — *Look for:* 2–3 role-specific questions about the work, team, growth and what success looks like; shows curiosity and homework; not googleable and not logistics (pay, benefits, hours) in an early round. Assess the *questions the user asks* — see §17 for the pool and the rubric note.
- **BE-18 [M]** Give me an example of a time you had a conflict with a team member. How did you handle it? — *Look for:* a conflict that was genuinely resolved; emotional maturity and no blame language; listening first, then a compromise or thoughtful escalation; a lesson learned or an improved relationship.
- **BE-19 [M]** Tell me about a mistake you made at work. How did you resolve it and what did you learn? — *Look for:* a meaningful mistake, not a trivial one; immediate ownership with no deflection; how it was discovered and fixed; a preventative measure or process change; ends on growth, not regret.
- **BE-20 [M]** Tell me about a time you took the initiative in your career. What was your motivation? — *Look for:* acted without being asked; a business reason beyond "it was interesting"; stakeholders brought along (not going rogue); measurable impact (time saved, quality, velocity).
- **BE-21 [S]** Describe a time you used leadership to motivate your team or colleagues. — *Look for:* leadership as service (clarity, removing blockers, recognition, leading by example); a specific influence on team behaviour; a team outcome; avoids the hero narrative.
- **BE-22 [M]** Tell me about a task you were responsible for but hadn't been trained on and weren't sure how to complete. — *Look for:* resourcefulness (docs, peers, code exploration, experiments); knowing when to ask for help; how fast and how well it was delivered; confidence now; pattern of "I may not have known X, but I knew how to approach learning it".
- **BE-23 [M]** Share a career goal you set and the steps you took to achieve it. — *Look for:* a goal actually pursued (visible in their work or portfolio); a deliberate plan, not passivity; what was gained; next milestone.
- **BE-24 [M]** Give an example of a difficult decision you had to make and how you handled it. — *Look for:* real stakes and trade-offs; structured thinking (data gathered, options weighed, stakeholders consulted); honest about downsides; the outcome and whether they'd decide the same again.
- **BE-25 [M]** Describe your process for solving problems. What steps do you take to resolve important issues at work? — *Look for:* a method, not "I just know": define the problem → gather data → form hypotheses → test systematically → communicate findings → prevent recurrence; backed by one concrete example; escalates and collaborates appropriately.
- **BE-26 [M]** Tell me about a time you disagreed with a direction from leadership or a lead. How did you handle it? — *Look for:* raised it respectfully with evidence and alternatives; heard the reasoning; disagree-and-commit once decided; no resentment or blame.
- **BE-27 [M]** Tell me about mentoring or helping a colleague grow. How do you mentor junior developers? — *Look for:* a specific person or situation; pairing, code review as teaching, delegating with support; the other person's measurable growth; patience and not doing the work for them.
- **BE-28 [M]** Tell me about the most difficult technical problem you solved. Walk me through it. — *Look for:* clear problem and impact; diagnosis steps and hypotheses; the fix and why it was chosen over alternatives; the outcome in numbers; what was documented or prevented afterwards.
- **BE-29 [M]** Tell me about a time you modernised legacy code. — *Look for:* why the change was needed; how risk was controlled (tests first, incremental, rollback); what was hardest; outcome and what the team could do afterwards that it couldn't before. (Complements AR-08.)
- **BE-30 [J]** What are your expectations of this role? — *Look for:* realistic, aligned with the posting (the work, growth, team); shows the user wants to contribute, not only to receive; no demands that clash with the job.
- **BE-31 [M]** If you started next week, what would you focus on in your first 30, 60 and 90 days? — *Look for:* listen and learn first (codebase, people, priorities), an early low-risk win, then a clearly scoped contribution; named priorities from the posting; "does that align with what you're envisioning?" as a check.
- **BE-32 [M]** What do you think is the main problem this role exists to solve, and how would you help? — *Look for:* has studied the business problem behind the job (why the role exists, what is costing time or money); links their experience to *outcomes*, not duties; avoids guessing wildly — frames it as "it sounds like… is that right?".
- **BE-33 [M]** Walk me through a specific project: the tools you used, your responsibilities, and what you delivered. — *Look for:* clear scope and the user's own role ("I" not "we"); stack and why it was chosen; deliverables and results, not just activities; honest about what was theirs vs the team's. (See SD-09 for the architecture-focused version.)
- **BE-34 [M]** How do you keep your skills current? What have you learned recently and which industry trends do you follow? — *Look for:* specific recent learning applied to real work or a project; a sustainable habit (courses, reading, side projects) rather than a list of buzzwords; judgement about what to adopt and what to ignore.
- **BE-35 [M]** This role looks narrower or less senior than your background. Why is it a good fit for you? — *Look for:* confident, un-defensive answer that frames experience as a time-and-cost-saving asset (productive quickly, minimal oversight, mentors others); genuine reasons for wanting the work; commitment and adaptability to this team.

**Picking `BE-` questions by role type** (use when building a set for a posting):

| If the role / posting emphasises… | Pull |
|---|---|
| Team leadership, mentoring | `BE-21`, `BE-27`, `BE-20`, `BE-23` |
| Incident response, on-call, support | `BE-25`, `BE-19`, `BE-05`, `BE-09` |
| Legacy modernisation | `BE-29`, `BE-20`, `BE-22`, `BE-24` |
| New technology / fast learning | `BE-22`, `BE-07`, `BE-19`, `BE-34` |
| Fast-growth / ambiguity | `BE-11`, `BE-20`, `BE-18`, `BE-24` |
| Cross-functional / stakeholder work | `BE-08`, `BE-06`, `BE-18`, `BE-26` |
| Ownership, concurrent projects | `BE-09`, `BE-20`, `BE-33`, `BE-31` |
| Phone screen / "hit the ground running" | `BE-01`, `BE-02`, `BE-30`, `BE-31`, `BE-32` |

## 14. System-design prompts (use whiteboard-style, 10–15 minutes)
Tags: `system-design` `architecture` `azure`

Approach to look for in every answer: **clarify requirements → sketch clients → API → services → data → map to concrete technologies → address scalability, security, cost, monitoring → state trade-offs.**

- **SD-01 [M]** Design a REST API and Angular/React front end for an order-management app. — *Look for:* entities and endpoints, auth and roles, relational schema, pagination, validation, caching, deployment.
- **SD-02 [S]** Design a file upload and processing pipeline on Azure. — *Look for:* direct-to-Blob upload, queue/event trigger, worker/function, status tracking, retries/idempotency, virus scan, large-file handling.
- **SD-03 [S]** Design a multi-tenant SaaS API. — *Look for:* tenant isolation options (database per tenant vs shared schema + tenant id), global query filters, per-tenant config, noisy neighbours, auth claims.
- **SD-04 [S]** Design a notification (email/SMS) system. — *Look for:* queue, templates, retries with backoff, idempotency, provider failover, user preferences, rate limits.
- **SD-05 [S]** Design rate limiting for a public API. — *Look for:* algorithm (token bucket/sliding window), shared store for multi-instance, 429 with `Retry-After`, fail-open vs fail-closed.
- **SD-06 [S]** Migrate a legacy Web Forms application to ASP.NET Core + a modern front end without downtime. — *Look for:* strangler routing, shared auth/session bridge, data stays put at first, page-by-page or feature-by-feature, rollback.
- **SD-07 [M]** Design a dashboard with real-time updates. — *Look for:* SignalR vs polling vs SSE, backplane, throttling updates, reconnection, auth on the hub.
- **SD-08 [S]** Integrate your application with an external CRM/ERP. — *Look for:* source of truth, sync direction, webhooks vs polling, conflict resolution, retries/idempotency, secrets and token management, mapping layer.
- **SD-09 [M]** Walk me through the architecture of the biggest system you've built: the problem, the design, why those technologies, and how you handled scale, security and monitoring. — *Look for:* a clear problem statement, a simple diagram-in-words (frontend → API → data → services), trade-offs behind each choice, resilience patterns, honest about what they personally designed vs inherited. Practise it as 5 minutes: problem (1) → architecture (2) → why (2) → scale/security/monitoring (2).

**Follow-up probes for any `SD-` answer** (use one or two, as an interviewer would):
- *Same design at 2× the scale — what breaks first and what changes?*
- *Same design with a different constraint — cheaper, faster, or more secure. What do you change?*
- *Explain this design to a non-technical stakeholder in two minutes.*

## 15. Lightning round (one-sentence answers — warm-up or quick drill)

- **LR-01** What does `[ApiController]` give you? — automatic model-validation 400s, binding-source inference, ProblemDetails.
- **LR-02** `IEnumerable` vs `List`? — abstraction for iteration (possibly lazy) vs concrete in-memory collection.
- **LR-03** `string` vs `StringBuilder`? — strings are immutable; use `StringBuilder` for many concatenations in loops.
- **LR-04** `readonly` vs `const`? — `const` compile-time inlined; `readonly` set at runtime in constructor.
- **LR-05** What is a primary key vs a foreign key vs a unique constraint? — row identity, relationship reference, uniqueness without being the identity.
- **LR-06** `DELETE` vs `TRUNCATE`? — logged row-by-row with filter and triggers vs deallocates pages, resets identity, no WHERE.
- **LR-07** `WHERE` vs `HAVING`? — filters rows before grouping vs filters groups after aggregation.
- **LR-08** Authentication token in header vs cookie? — header needs explicit attach (immune to CSRF, XSS-exposed if stored in JS); cookie sent automatically (needs CSRF protection, can be `httpOnly`).
- **LR-09** `Task` vs `ValueTask`? — `ValueTask` avoids an allocation when results are often synchronous; don't await twice.
- **LR-10** Singleton pattern vs singleton service lifetime? — pattern is a hand-rolled global instance; DI singleton is managed lifetime — prefer DI.
- **LR-11** What is idempotency? — repeating the operation has the same effect as doing it once.
- **LR-12** What is a race condition? — outcome depends on unsynchronised timing of concurrent operations.
- **LR-13** Git `merge` vs `rebase`? — merge preserves history with a merge commit; rebase rewrites your commits onto a new base (don't rebase shared branches).
- **LR-14** What is CORS? — browser mechanism restricting cross-origin requests; server opts in via headers; not a substitute for auth.
- **LR-15** What is technical debt? — shortcuts whose cost compounds as "interest" in slower, riskier change; manage deliberately.

---

## 16. AI-assisted development and AI integration
Tags: `ai` `llm` `copilot` `prompt-engineering` `openai` `rag` `ai-agents` `generative-ai`

- **AI-01 [M]** Tell me about your experience with AI tools in your development work. — *Look for:* specific tools and specific uses (completion, tests, refactoring, explaining code), what it is good and bad at, human review and tests as the safety net; no vague "I use AI a lot". (See also BE-15.)
- **AI-02 [M]** How would you integrate an AI/LLM feature into an existing system? — *Look for:* clear use case first; call via a service layer with secrets in a vault; grounding the model with the company's own data (retrieval/RAG) rather than relying on its memory; structured outputs and validation; latency, cost and rate-limit handling; fallbacks and a human-in-the-loop where stakes are high; logging and evaluation.
- **AI-03 [M]** What is your approach to prompt engineering? — *Look for:* clear role, context, task and output format; examples; iterate against test cases rather than by feel; version and review prompts like code; separate instructions from untrusted input.
- **AI-04 [S]** What are the main risks of putting an LLM in a production application and how do you mitigate them? — *Look for:* hallucination (grounding, citations, validation), prompt injection (treat model input as untrusted, least-privilege tools), data privacy/PII, cost and latency, non-determinism (evaluation sets, regression checks), vendor and model-version change.

## 17. Questions to ask the interviewer
Tags: `questions-to-ask` `behavioural`

Used to assess `BE-17`: the user states the 2–3 questions they would ask, and the assessor scores them with the **questions-to-ask note in the rubric (§3)**. These are a *pool to draw from and adapt* — the strongest versions are specific to the posting and interviewer. Rules: at least two questions, show curiosity about the work, team and hiring manager, **no logistics** (pay, benefits, schedule) in an early round.

Team-and-leadership questions (best for a hiring manager or team lead):
- **QA-01** Can you tell me about someone on your team whose career has grown since they started working with you? What did that look like?
- **QA-02** Can you tell me about a time someone on your team was struggling? How did you approach that?
- **QA-03** Can you tell me about a recent decision that affected your team? How did you communicate it and get people on board?
- **QA-04** Can you tell me about a time your team disagreed with a direction from leadership? How did you handle it?
- **QA-05** What does giving feedback look like on this team? Can you share a recent example where you gave someone constructive criticism?
- **QA-06** Can you tell me about a time the team was really stretched thin? How did you manage workload during that period?
- **QA-07** What is the most common reason people leave this team or don't make it past the first year? *(Bold — only after the first round.)*

Performance-expectation questions (best for any interviewer):
- **QA-08** What would make someone exceed expectations in this role in the first six months?
- **QA-09** What measurable outcomes define success here?
- **QA-10** What does success look like in the first 90 days?
- **QA-11** What is the biggest problem you hope the person in this role will solve? *(Pair with BE-32.)*

Closing moves (end the conversation like a problem-solver, not someone waiting for approval):
- **QA-12** *Consultant close:* "It sounds like [problem] and [goal] are top of mind for your team. If I were starting next week, I'd focus on [specific priority]. Does that align with what you're envisioning for the role?" — *Look for:* names the actual problem from the conversation, offers a specific first priority, and checks alignment instead of asking for approval.
- **QA-13** *Open the door to concerns:* "Is there any area where I could elaborate on how I'd approach this role?" — *Look for:* confident, prepared, solutions-focused; invites concerns without sounding defensive; the user then answers whatever comes up with evidence and a reframe.

---

## Sources (researched 2026-10-19)

Question topics were compiled from these pages; "Look for" notes were written from them plus standard practice. Verify version-specific details (HybridCache, EF Core 10 features, render modes) against Microsoft Learn before quoting them as fact in an interview.

- [CodeWithMukesh — .NET interview questions](https://codewithmukesh.com/blog/dotnet-interview-questions/)
- [CodeWithMukesh — EF Core interview questions](https://codewithmukesh.com/blog/efcore-interview-questions/)
- [Hyring — Top 60 ASP.NET interview questions (2026)](https://hyring.com/jobseeker-toolkit/interview-questions/technical/asp-net)
- [Hyring — Top 60 .NET interview questions (2026)](https://hyring.com/jobseeker-toolkit/interview-questions/technical/dot-net)
- [roadmap.sh — Top 50 full stack developer interview questions](https://roadmap.sh/questions/full-stack)
- [Interview Kickstart — .NET interview questions](https://interviewkickstart.com/interview-questions/skills/dotnet-interview-questions)
- [Dot Net Tutorials — ASP.NET Core Web API intermediate interview questions](https://dotnettutorials.net/lesson/asp-net-core-web-api-intermediate-interview-questions-and-answers/)

Sections 7 (SQL Server) and the Angular/RxJS/NgRx items in section 8 were not covered by the sources and were written from standard practice.

**The candidate's own interview notes (added 2026-10-19):** questions to ask the interviewer, common and behavioural question lists, a behavioural question library with STAR guidance, the recruiter's prep notes, "Rules of Interviewing", and the interview-skills guide. Used for: `BE-18`–`BE-35`, `TE-08`, `SE-09`, `CL-11`/`CL-12`, `PR-07`, `SD-09` and its probes, `AI-01`–`AI-04`, and §17. Questions that were already covered were folded into the existing entry as an "Alt" wording rather than duplicated. **Deliberately excluded:** scripted answers, personal facts, and course/cert counts — answers and evidence always come from the profile at run time, so this file stays role-generic and stays correct as the profile changes.
