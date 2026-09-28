# EngBrain

**AI Engineering Organizational Memory Agent**

> “EngBrain doesn’t just understand your code. It remembers why your code became the way it is.”

## What it does

EngBrain answers three questions every engineer asks:

1. **Why does this code exist?**
2. **Have we seen this problem before?**
3. **What should I know before changing this?**

The differentiator is **persistent Hindsight memory**: commits, PRs, incidents, deployments, root causes, fixes, and architecture decisions — linked and searchable.

## Architecture

```
GitHub + Engineering Data
          ↓
   Hindsight Memory
          ↓
   Engineering Agent
          ↓
       /ask API
          ↓
      Frontend UI
```

## Quick start

```bash
cd engbrain/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000**

## Core demo (2 minutes)

1. Open the **Dashboard** → click the demo buttons, or go to **Ask EngBrain**.
2. Ask:

   > Why does the retry logic in payment_service.py exist?

   EngBrain traces: **Code → Commit → PR → Incident → Root Cause → Fix** (INC-2025-0310 → PR-42 → ADR-007).

3. Then ask:

   > What should I know before changing the retry logic in payment-service?

   The answer combines GitHub history, three incidents, deployments, ADR-007, and Hindsight lessons (max attempts = 3, circuit breaker required, retry-rate is a leading indicator).

### Hindsight growth path

| Interaction | Question | What memory contributes |
|-------------|----------|-------------------------|
| 1 | What happened with payment-service? | Service history + incidents |
| 5 | Have we seen this timeout before? | Similar-incident search |
| 10 | What caused previous failures? | Root causes + linked PRs |
| 20 | What should I know before changing this? | Full evidence graph |

## Sample data

5 services · 8 commits · 8 PRs · 5 incidents · 8 deployments · 3 ADRs · 5 memory lessons

Canonical relationship for the core demo:

```
PR-42 → Commit a1b2c3 → payment-service → Deploy v2.4.0
       → INC-2025-0310 → Root cause (no backoff) → Fix (exponential backoff)
       → ADR-007 (retry policy)
```

Later refinements: PR-87 (max attempts 5→3 after latency regression), PR-112 (circuit breaker after thundering herd), PR-134 (retry metrics).

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ask` | Ask EngBrain (body: `{ "question": "..." }`) |
| GET | `/api/health` | Memory stats |
| GET | `/api/services` | List services |
| GET | `/api/services/{id}` | Full service history |
| GET | `/api/incidents` | List incidents |
| GET | `/api/incidents/{id}` | Incident + related PRs/commits |
| GET | `/api/timeline` | Unified engineering timeline |
| GET | `/api/memory` | Hindsight lessons |
| GET | `/api/tools` | Agent tool catalogue |

Answers always include **source IDs**. Historical facts are never invented — only retrieved.

## Agent tools

- `search_memory` — keyword search across all Hindsight stores
- `get_file_history` — commits that touched a file
- `find_similar_incidents` — past incidents matching a problem description
- `get_service_history` — commits, PRs, incidents, deployments, ADRs, lessons
- `get_deployment_history` — recent deploys

## Project layout

```
engbrain/
├── backend/
│   ├── main.py          # FastAPI app + routes
│   ├── agent.py         # Tools + grounded answer synthesis
│   ├── data_loader.py   # Sample data + indexes
│   └── requirements.txt
├── data/
│   └── sample_data.json # Connected realistic history
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── README.md
```

## Team split (hackathon)

| Person | Owns |
|--------|------|
| 1 | Hindsight memory, agent tools, `/ask` API |
| 2 | Sample data model, frontend UI |

Keep it small, polished, and demo-ready. No unnecessary infrastructure.
