# 10 — Product/Architecture Decisions, Risks and Roadmap

## Key decisions

### 1. Keep Detect → Capture → Verify

This is the differentiator. Removing Verify would make the product closer to “gap detection + note capture,” while verification proves the captured knowledge can be applied.

### 2. Do not position the detector as proving tacit knowledge

Evidence can justify a targeted question, not prove a person's private knowledge state. Human confirmation is the epistemic boundary.

### 3. Use realistic fixture adapters before live integrations

Product value is in the inference/capture/verification loop. Live OAuth, rate limits and permissions can consume the entire hackathon without proving that value.

A fixture adapter is not “fake architecture” if it consumes provider-shaped JSON and emits the same normalized contract as a future live adapter.

### 4. Keep GitHub live adapter as stretch

A GitHub adapter is useful because PR/review data is engineering-native and relatively structured, but it should never block the main demo.

### 5. PostgreSQL as target persistence

PostgreSQL matches the lifecycle's need for transactions, constraints, immutable history, JSONB metadata and future concurrent use. It also prevents documentation from describing SQLite while the intended implementation is already PostgreSQL.

### 6. OKF as portable output, not transactional database

Use PostgreSQL for workflow truth and OKF for exchange. This gives portability without forcing all state into Markdown.

### 7. Multi-agent for development, not runtime product architecture

There is little product value in making SiloBreaker's inference itself a swarm of agents for the MVP. Multi-agent concurrency is more defensible in the Codex engineering harness: FE, BE, AI/data and reviewer work independently against shared contracts.

## Product risks

| Risk | Mitigation |
|---|---|
| False “missing knowledge” claim | call findings candidates; show inspected sources; separate confidence; require expert confirmation |
| Correlation mistaken for expertise | count substantive actor/action events, not name mentions/authorship alone |
| Missing import mistaken for no documentation | source inventory + unknown state when coverage is incomplete |
| Duplicate artifacts inflate risk | parent/event linking and deterministic de-duplication |
| Model invents citation | chunk IDs + quote membership validation |
| Model invents procedure | expert capture is new input; structurer cannot add facts; approval required |
| Exercise tests invented requirement | every criterion maps to approved knowledge; expert review before release |
| Unsafe answer accidentally passes | critical criteria + deterministic aggregate rule + uncertainty state |
| Prompt injection in evidence | treat source as data; no model tools; output validation; adversarial tests |
| Demo depends on external APIs | local fixtures are the primary path; live adapter is stretch |

## Technical risks

| Risk | Mitigation |
|---|---|
| Parallel agents collide on contracts | freeze shared contracts; worktrees; serialize schema-changing tasks |
| PostgreSQL setup slows build | one Docker/local instance with one migration path; avoid advanced infra |
| AI output variability | typed schemas, bounded retries, fake-model tests, small real-model semantic set |
| Long AI latency | bounded corpus, two-stage detection, explicit deadline, progress/error state |
| Oracle leakage | physically separate `fixtures/input` from `fixtures/oracle`; test actual payload |

## Future roadmap

### Team pilot

- authentication and authorization;
- read-only GitHub/Slack/Jira connectors;
- permission-aware retrieval;
- source retention/deletion rules;
- independent review of captured procedures.

Validate: are candidate questions useful enough to justify the correction burden?

### Repeated use

- incremental ingestion;
- knowledge freshness;
- supersession/re-verification;
- scheduled continuity review.

Validate: how quickly does approved knowledge become stale?

### Larger corpus

- background workers only when synchronous operations become insufficient;
- lexical/vector retrieval to reduce model context;
- source ACL propagation;
- benchmark corpus spanning several services.

Validate: does retrieval improve cost/latency without hiding important evidence?

### Organization scale

- tenant isolation;
- centralized connector management;
- stronger audit/access controls;
- quality dashboards focused on system evidence quality, not employee scoring.

### Advanced knowledge relationships

Consider graphs only if real usage shows that relationship traversal improves detection/transfer over simpler evidence linking and OKF cross-links.

## Open questions to resolve before D-Day implementation

1. Which exact model/API credentials are guaranteed at the event?
2. Will PostgreSQL be local/native or Dockerized on team laptops?
3. What is the smallest provider-shaped corpus that reliably demonstrates one real gap and three negative controls?
4. Which frontmatter subset of OKF v0.2 will be implemented and validated in tests?
5. Which API/types must be frozen before FE/BE/AI agents split into parallel worktrees?
6. What is the fallback demo behavior if the model provider is unavailable?
