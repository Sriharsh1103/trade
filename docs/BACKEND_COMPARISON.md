# Backend Technology Comparison: Rust vs Node vs Go

Analysis for a low-latency forex trading backend targeting Exness/MT5 integration.

## Requirements

| Requirement | Weight | Notes |
|-------------|--------|-------|
| Order execution latency | High | But retail forex is broker-bound |
| Concurrent position monitoring | High | Multiple symbols, trailing stops |
| Risk validation speed | High | Must run before every order |
| MT5 integration | Critical | No native bindings in any language |
| ML strategy integration | Medium | Python training, signal delivery |
| Development velocity | Medium | Phase 1 needs fast iteration |
| Operational simplicity | Medium | Docker deployment on Linux |

## Latency Reality Check

Retail forex latency breakdown (typical):

```
Network to broker:     20–100 ms
MT5 terminal processing: 10–50 ms
Broker matching engine:  10–100 ms
Our backend overhead:    < 1 ms (any of Rust/Go/Node)
─────────────────────────────────
Total:                   50–250 ms
```

The **bottleneck is MT5 terminal + broker**, not our backend language. Sub-millisecond backend optimization only matters for HFT — not retail forex.

## Comparison

### Rust

| Pros | Cons |
|------|------|
| Lowest latency, zero-cost abstractions | Slower development velocity |
| Memory safety without GC pauses | No MT5 native bindings |
| Excellent for hot-path risk engine | Steeper learning curve |
| Deterministic performance | Harder to iterate in Phase 1 |

**Verdict:** Best for pure execution engines at scale. Overkill for Phase 1 where integration speed matters more.

### Node.js (TypeScript)

| Pros | Cons |
|------|------|
| Fastest to prototype | GC pauses under load |
| Rich npm ecosystem | Single-threaded event loop limits CPU-bound work |
| Easy HTTP/WebSocket APIs | Not typical choice for trading systems |
| Good for orchestration layer | Type safety requires discipline (TS helps) |

**Verdict:** Good for a web dashboard or strategy orchestrator, not the core trading engine.

### Go

| Pros | Cons |
|------|------|
| ~Rust-level performance for our use case | Less ecosystem for quant finance vs Python |
| Goroutines ideal for position monitoring | No MT5 native bindings (same as all) |
| Single static binary, easy Docker deploy | Generics still maturing |
| Strong stdlib for HTTP/gRPC/JSON | |
| Fast compilation, good dev velocity | |
| Built-in race detector for concurrent code | |

**Verdict:** Best balance for this project.

## Recommendation: Go

### Rationale

1. **Latency sufficient** — Go handles 100K+ req/s; we need ~10–100 orders/min max
2. **Concurrency model** — goroutines per open position for real-time SL/TP monitoring
3. **Deployment** — single binary alongside MT5 Docker container
4. **Integration** — HTTP client to MT5 REST bridge; gRPC/HTTP server for Python strategy service
5. **Risk engine** — deterministic, fast enough without Rust complexity
6. **Phase 1 velocity** — scaffold and iterate faster than Rust

### Hybrid Architecture (Future)

```
┌─────────────────────────────────────────────────┐
│ Go Trading Core (this repo)                     │
│  • Risk validation                              │
│  • Order routing                                │
│  • Position monitoring                          │
│  • Demo engine                                  │
│  • HTTP/gRPC API                                │
└───────────────────────┬─────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
  MT5 REST Bridge   Python Strategy   Web Dashboard
  (Docker)          (ML training)     (Node/React - future)
```

If latency becomes critical at scale, extract the risk hot-path to Rust as a shared library — but only after profiling proves Go is the bottleneck (unlikely for retail forex).

## What We Implemented

- **Go backend** in `backend/` with modular packages
- **Python strategy placeholder** in `strategy/` for Phase 2 ML
- **Demo mode** in Go (no external dependencies for Phase 1 testing)
