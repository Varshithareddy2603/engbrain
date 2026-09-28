"""EngBrain API — Engineering Organizational Memory Agent."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Any

from data_loader import store
from agent import ask, TOOLS, review_change

app = FastAPI(
    title="EngBrain",
    description="AI Engineering Organizational Memory Agent — remembers why your code became the way it is.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    question: str
    answer: str
    historical_context: list[str]
    related_incidents: list[dict[str, Any]]
    github_evidence: list[dict[str, Any]]
    deployments: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    evidence_count: int




class ReviewChangeRequest(BaseModel):
    service: str = Field(..., min_length=1, max_length=200)
    change_summary: str = Field(..., min_length=1, max_length=4000)
    files: list[str] = Field(default_factory=list)


@app.post("/api/review-change")
def api_review_change(body: ReviewChangeRequest):
    """Incident-Aware Code Review: compare a change with Hindsight memory."""
    return review_change(body.service, body.change_summary, files=body.files or [])

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "EngBrain",
        "tagline": "EngBrain doesn’t just understand your code. It remembers why your code became the way it is.",
        "memory_stats": store.memory_stats(),
    }


@app.post("/api/ask", response_model=AskResponse)
def api_ask(body: AskRequest):
    """Ask EngBrain a question. Answers are grounded in Hindsight memory with source IDs."""
    result = ask(body.question)
    return result


@app.get("/api/services")
def list_services():
    return store.services


@app.get("/api/services/{service_id}")
def get_service(service_id: str):
    hist = store.get_service_history(service_id)
    if not hist.get("service"):
        # try by name
        svc = store.get_service_by_name(service_id)
        if not svc:
            raise HTTPException(404, "Service not found")
        hist = store.get_service_history(svc["id"])
    return hist


@app.get("/api/incidents")
def list_incidents():
    return sorted(store.incidents, key=lambda i: i["started_at"], reverse=True)


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    inc = store.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    # Enrich with related entities
    related = {
        "prs": [store.get(pid) for pid in inc.get("related_pr_ids", []) if store.get(pid)],
        "commits": [store.get(cid) for cid in inc.get("related_commit_ids", []) if store.get(cid)],
        "deployments": [store.get(did) for did in inc.get("related_deployment_ids", []) if store.get(did)],
    }
    return {"incident": inc, "related": related}


@app.get("/api/timeline")
def timeline(limit: int = 60):
    """Unified engineering timeline for the dashboard."""
    events = []
    for inc in store.incidents:
        events.append({
            "id": inc["id"],
            "type": "incident",
            "title": inc["title"],
            "time": inc["started_at"],
            "severity": inc["severity"],
            "service_id": inc["service_id"],
        })
    for dep in store.deployments:
        events.append({
            "id": dep["id"],
            "type": "deployment",
            "title": f"Deploy {dep['version']}",
            "time": dep["deployed_at"],
            "service_id": dep["service_id"],
            "status": dep["status"],
            "notes": dep.get("notes"),
        })
    for pr in store.pull_requests:
        events.append({
            "id": pr["id"],
            "type": "pr",
            "title": pr["title"],
            "time": pr["merged_at"],
            "service_id": pr["service_id"],
            "number": pr["number"],
        })
    for issue in store.issues:
        events.append({
            "id": issue["id"],
            "type": "issue",
            "title": issue["title"],
            "time": issue.get("created_at") or "",
            "service_id": issue["service_id"],
            "state": issue.get("state"),
        })
    for rb in store.rollbacks:
        events.append({
            "id": rb["id"],
            "type": "rollback",
            "title": rb["title"],
            "time": rb["rolled_back_at"],
            "service_id": rb["service_id"],
            "reason": rb.get("reason"),
        })
    for o in store.outcomes:
        events.append({
            "id": o["id"],
            "type": "outcome",
            "title": o["title"],
            "time": o["date"],
            "service_id": o["service_id"],
            "success": o.get("success"),
        })
    for adr in store.architecture_decisions:
        events.append({
            "id": adr["id"],
            "type": "adr",
            "title": adr["title"],
            "time": adr["date"],
            "service_id": adr["service_id"],
            "status": adr["status"],
        })
    events.sort(key=lambda e: e["time"], reverse=True)
    return events[:limit]


@app.get("/api/memory")
def list_memory():
    return store.memory_entries


@app.get("/api/issues")
def list_issues():
    return store.get_issues(limit=50)


@app.get("/api/reviews")
def list_reviews():
    return store.get_reviews(limit=50)


@app.get("/api/rollbacks")
def list_rollbacks():
    return store.get_rollbacks(limit=50)


@app.get("/api/outcomes")
def list_outcomes():
    return store.get_outcomes(limit=50)


@app.get("/api/tools")
def list_tools():
    return {
        "tools": list(TOOLS.keys()),
        "description": {
            "search_memory": "Search Hindsight memory across all entity types",
            "get_file_history": "Return commits that touched a given file",
            "find_similar_incidents": "Find past incidents similar to the described problem",
            "get_service_history": "Full history for a service (incl. issues, reviews, rollbacks, outcomes)",
            "get_deployment_history": "Recent deployments, optionally filtered by service",
            "get_issues": "GitHub-style issues linked to PRs and incidents",
            "get_reviews": "PR reviews",
            "get_rollbacks": "Past rollbacks and config reversions",
            "get_outcomes": "Measured outcomes after fixes and experiments",
        },
    }


# Serve frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")
