## 17. Implementation Blueprint

### 17.1 Repository Layout

```
markdown-summary-tool/
├── src/
│   ├── gateway/           # HTTP handler, auth, rate limiting
│   ├── validator/         # Request schema validation
│   ├── resolver/          # Data connectors (table, file, handle, url, inline)
│   ├── normalizer/        # JSON flattening, pagination, schema union
│   ├── profiler/          # Column stats over full data
│   ├── planner/           # Fact planning (rule-based + LLM)
│   ├── engine/            # DuckDB/pandas execution
│   ├── prose/             # LLM prose generation
│   ├── verifier/          # Number extraction + fact matching
│   ├── sanitizer/         # Markdown sanitization
│   ├── artifacts/         # Artifact store
│   ├── cache/             # Profile/fact/plan cache
│   └── models/            # Data models (request, fact, envelope)
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── eval/              # Evaluation set + harness
│   └── security/          # Adversarial tests
├── config/
│   └── default.yaml
├── eval/
│   └── cases/             # 115 eval cases
└── docs/
    └── api.md
```

### 17.2 Data Models (Excerpt)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Fact:
    id: str
    kind: str  # count, aggregate, ranking, trend, comparison, anomaly, distribution
    metric: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    slice: Optional[dict] = None
    provenance: Optional[dict] = None
    tolerance: float = 0.01
    caveat: Optional[str] = None

@dataclass
class FactSet:
    facts: list[Fact]
    computed_at: str
    total_engine_ms: int

@dataclass
class SectionPlan:
    heading: str
    fact_ids: list[str]
    budget: str  # e.g., "2-3 sentences", "1 paragraph + table"

@dataclass
class SummaryRequest:
    datasets: list[Dataset]
    request: str
    relationships: list[Relationship] = None
    options: Options = None
    prior_summary_id: Optional[str] = None
    edit_instruction: Optional[str] = None
```

### 17.3 Orchestration (Excerpt)

```python
async def create_summary(req: SummaryRequest) -> Envelope:
    # Stage 0-1: Validate, resolve, normalize, profile
    normalized = await validate_and_resolve(req)
    tables = await normalize(normalized)
    profiles = await profile_all(tables)

    # Stage 2-3: Plan facts, execute
    fact_specs = plan_facts(profiles, req)
    fact_set = await engine.execute(fact_specs, tables)

    # Stage 4-5: Plan markdown, generate prose
    section_plan = await plan_sections(fact_set, req)
    markdown = await generate_prose(fact_set, section_plan, req)

    # Stage 6-7: Verify, repair if needed
    result = verifier.verify(markdown, fact_set)
    if not result.passed:
        markdown = await repair(markdown, result.failures, fact_set)
        result = verifier.verify(markdown, fact_set)
        if not result.passed:
            markdown = fallback_render(result.failures, fact_set, markdown)

    # Stage 8-9: Sanitize, package
    markdown = sanitizer.sanitize(markdown)
    return package(markdown, fact_set, profiles, result)
```

### 17.4 Verifier Sketch (Excerpt)

```python
import re

NUMBER_RE = re.compile(r''\$?[\d,]+(?:\.\d+)?%?(?:[KMB])?'')

def verify(markdown: str, fact_set: FactSet) -> VerifyResult:
    numbers = extract_numbers(markdown)
    failures = []
    for num in numbers:
        matched = False
        for fact in fact_set.facts:
            if matches(num, fact):
                matched = True
                break
        if not matched:
            failures.append(Failure(number=num, location=num.location))
    return VerifyResult(passed=len(failures) == 0, failures=failures)

def matches(num: ExtractedNumber, fact: Fact) -> bool:
    # Normalize both to same scale and compare within tolerance
    return abs(num.value - fact.value) <= fact.tolerance * max(abs(fact.value), 1)
```

### 17.5 Sanitizer Sketch (Excerpt)

```python
import re

STRIP_PATTERNS = [
    re.compile(r''<[^>]+>''),           # HTML tags
    re.compile(r''javascript:'', re.I),  # JS URIs
    re.compile(r''data:'', re.I),        # Data URIs
    re.compile(r''on\w+\s*='', re.I),   # Event handlers
]

def sanitize(markdown: str) -> str:
    for pat in STRIP_PATTERNS:
        markdown = pat.sub('''', markdown)
    return markdown
```

### 17.6 Dependencies

| Dependency | Purpose | Notes |
|---|---|---|
| DuckDB | Data engine (primary) | In-process, no server |
| pandas | Data engine (fallback) | For small data |
| reportlab / pymupdf | Not needed at runtime | Only for spec PDF generation |
| LLM provider SDK | Prose generation | Configurable (OpenAI, Anthropic, etc.) |
| jsonschema | Request validation | |
| markdown-it / CommonMark | Markdown parsing (verifier) | |


### 17.7 Detailed Module Contracts

Each connector implements resolve(ref) -> Table. Connectors are registered in a map keyed by ref.kind. Adding a new connector requires only implementing this interface and registering it. The engine translates FactSpec into SQL (DuckDB) or pandas operations, executes, and wraps results in Fact records with provenance. The verifier is a pure function: verify(markdown, facts) -> VerifyResult with no LLM or I/O.

### 17.8 Testing Strategy per Module

| Module | Test Type | Key Cases |
|---|---|---|
| Validator | Unit | Schema valid/invalid, edge cases (empty, huge, special chars) |
| Resolver | Integration | Each connector with real/mocked data source |
| Normalizer | Unit | Nested JSON depth 1-5, pagination, schema union |
| Profiler | Unit + perf | Correctness on known data, speed on 1M rows |
| Engine | Unit + integration | Each fact kind, SQL injection attempt, large data |
| Prose | Integration | Grounding (no hallucinated numbers), style, locale |
| Verifier | Unit | 87 cases (see 9.9) |
| Sanitizer | Security | XSS payloads, HTML injection, JS URIs |

### 17.9 Build and Release

CI pipeline: lint (ruff + mypy) -> test (pytest --cov) -> eval (faithfulness gate) -> security (bandit + adversarial) -> build (docker) -> deploy (helm). Release is gated on: all tests pass, eval faithfulness gate passes (100pct numeric accuracy on eval set), security tests pass. No release proceeds with a failing faithfulness gate.

### 17.10 Dependency Rationale

| Dependency | Why This One | Alternative Considered |
|---|---|---|
| DuckDB | In-process, fast, no server, handles JSON/CSV/Parquet natively | pandas (fallback), Spark (overkill) |
| jsonschema | Standard, well-tested JSON Schema validation | pydantic (heavier, but viable) |
| markdown-it | CommonMark-compliant parsing for verifier | mistune, cmark (also viable) |
| LLM SDK | Provider-agnostic via config | Hardcoded provider (rejected) |
| Redis (optional) | Cache backing for multi-instance | In-memory only (single instance) |
| S3/GCS (optional) | Artifact store for large tables | Local filesystem (single instance) |

All dependencies are pinned in requirements.txt with hashes. No dependency has access to raw data beyond what the tool passes it.

### 13.6 Module Dependency Graph

```
                    +------------------+
                    |   Gateway (API)  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v------+ +----v-----+ +-----v------+
     |  Connector    | | Normalizer| |  Profiler  |
     |  (per type)   | |           | |            |
     +--------+------+ +-----+-----+ +-----+------+
              |              |              |
              +--------------+--------------+
                             |
                    +--------v---------+
                    |  Fact Planner    |
                    |  (rule + LLM)    |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Data Engine     |
                    |  (DuckDB/pandas) |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Markdown Planner|
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Prose Generator |
                    |  (LLM call)      |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Verifier        |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Sanitizer       |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Response        |
                    |  Assembler       |
                    +------------------+
```

Each module has a single responsibility and communicates via well-defined interfaces (fact specs, fact sets, markdown plans). No module directly calls another -- the orchestrator (pipeline controller) sequences them.

### 13.7 Build and Deployment Pipeline

| Stage | Tool | Purpose |
|---|---|---|
| Lint | ruff, mypy | Code quality and type checking |
| Test | pytest | Unit, integration, and eval tests |
| Build | Docker | Container image with all dependencies |
| Scan | Trivy, pip-audit | Vulnerability scanning |
| Deploy | Kubernetes / ECS | Rolling deployment with health checks |
| Verify | Smoke tests | Post-deploy verification of key flows |

CI runs on every pull request. Deployment to production requires manual approval after staging verification.

### 13.8 Configuration Reference

| Config Key | Default | Description |
|---|---|---|
| `llm.provider` | openai | LLM provider (openai, anthropic, google) |
| `llm.model` | gpt-4o-mini | Model name |
| `llm.timeout` | 30s | LLM call timeout |
| `llm.max_retries` | 2 | Max retry attempts |
| `engine.type` | duckdb | Engine type (duckdb, pandas) |
| `engine.memory_limit` | 2GB | Max memory for DuckDB |
| `cache.ttl` | 1h | Cache time-to-live |
| `cache.max_size` | 1000 | Max cached entries |
| `artifact.ttl` | 24h | Artifact retention |
| `artifact.backend` | filesystem | Artifact storage (filesystem, s3) |
| `limits.max_rows` | 10M | Max rows per dataset |
| `limits.max_datasets` | 8 | Max datasets per request |
| `limits.max_pages` | 1000 | Max pages for URL connector |

Configuration is via environment variables or config file. Secrets (API keys) are via environment variables only, never in config files.

### 13.9 Monitoring and Alerting

| Metric | Alert Threshold | Action |
|---|---|---|
| Error rate > 5% | 5 min window | Page on-call |
| p95 latency > 15s | 10 min window | Investigate; check LLM provider |
| Verification failure rate > 10% | 15 min window | Check LLM output quality |
| LLM cost spike > 2x daily average | 1 hour window | Check for abuse or misconfiguration |
| Disk usage > 80% | Immediate | Clean artifacts; scale storage |

Alerts are routed via PagerDuty (SEV-1/2) or Slack (SEV-3).

### 13.10 Development Workflow

1. **Branch:** Feature branch from main.
2. **Code:** Implement with tests (TDD encouraged).
3. **Review:** Pull request with at least one reviewer.
4. **CI:** All checks must pass (lint, test, eval subset).
5. **Merge:** Squash merge to main.
6. **Deploy:** Auto-deploy to staging; manual promotion to production.
7. **Verify:** Smoke tests and eval suite on staging before promotion.

