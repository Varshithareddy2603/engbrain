"""Load and index sample engineering data for Hindsight memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_data.json"


def _time_key(item: dict) -> str:
    return (
        item.get("date")
        or item.get("merged_at")
        or item.get("started_at")
        or item.get("deployed_at")
        or item.get("created_at")
        or item.get("rolled_back_at")
        or item.get("submitted_at")
        or item.get("closed_at")
        or ""
    )


class EngineeringDataStore:
    def __init__(self) -> None:
        with open(DATA_PATH) as f:
            raw = json.load(f)

        self.services: list[dict] = raw["services"]
        self.commits: list[dict] = raw["commits"]
        self.pull_requests: list[dict] = raw["pull_requests"]
        self.issues: list[dict] = raw.get("issues", [])
        self.reviews: list[dict] = raw.get("reviews", [])
        self.incidents: list[dict] = raw["incidents"]
        self.deployments: list[dict] = raw["deployments"]
        self.rollbacks: list[dict] = raw.get("rollbacks", [])
        self.outcomes: list[dict] = raw.get("outcomes", [])
        self.architecture_decisions: list[dict] = raw["architecture_decisions"]
        self.memory_entries: list[dict] = raw["memory_entries"]

        self._by_id: dict[str, dict] = {}
        for collection in (
            self.services,
            self.commits,
            self.pull_requests,
            self.issues,
            self.reviews,
            self.incidents,
            self.deployments,
            self.rollbacks,
            self.outcomes,
            self.architecture_decisions,
            self.memory_entries,
        ):
            for item in collection:
                self._by_id[item["id"]] = item

        self._commits_by_service: dict[str, list] = {}
        self._prs_by_service: dict[str, list] = {}
        self._issues_by_service: dict[str, list] = {}
        self._reviews_by_service: dict[str, list] = {}
        self._reviews_by_pr: dict[str, list] = {}
        self._incidents_by_service: dict[str, list] = {}
        self._deps_by_service: dict[str, list] = {}
        self._rollbacks_by_service: dict[str, list] = {}
        self._outcomes_by_service: dict[str, list] = {}
        self._adrs_by_service: dict[str, list] = {}
        self._mem_by_service: dict[str, list] = {}
        self._commits_by_file: dict[str, list] = {}

        for c in self.commits:
            self._commits_by_service.setdefault(c["service_id"], []).append(c)
            for f in c.get("files", []):
                self._commits_by_file.setdefault(f, []).append(c)

        for p in self.pull_requests:
            self._prs_by_service.setdefault(p["service_id"], []).append(p)
        for i in self.issues:
            self._issues_by_service.setdefault(i["service_id"], []).append(i)
        for r in self.reviews:
            self._reviews_by_service.setdefault(r["service_id"], []).append(r)
            self._reviews_by_pr.setdefault(r["pr_id"], []).append(r)
        for i in self.incidents:
            self._incidents_by_service.setdefault(i["service_id"], []).append(i)
        for d in self.deployments:
            self._deps_by_service.setdefault(d["service_id"], []).append(d)
        for r in self.rollbacks:
            self._rollbacks_by_service.setdefault(r["service_id"], []).append(r)
        for o in self.outcomes:
            self._outcomes_by_service.setdefault(o["service_id"], []).append(o)
        for a in self.architecture_decisions:
            self._adrs_by_service.setdefault(a["service_id"], []).append(a)
        for m in self.memory_entries:
            self._mem_by_service.setdefault(m["service_id"], []).append(m)

        for d in (
            self._commits_by_service,
            self._prs_by_service,
            self._issues_by_service,
            self._reviews_by_service,
            self._incidents_by_service,
            self._deps_by_service,
            self._rollbacks_by_service,
            self._outcomes_by_service,
            self._adrs_by_service,
            self._mem_by_service,
            self._commits_by_file,
            self._reviews_by_pr,
        ):
            for k in d:
                d[k].sort(key=_time_key, reverse=True)

    def get(self, entity_id: str) -> dict | None:
        return self._by_id.get(entity_id)

    def get_service_by_name(self, name: str) -> dict | None:
        name_l = name.lower().replace("_", "-").replace(" ", "-")
        for s in self.services:
            if s["name"].lower() == name_l or s["id"] == name_l or name_l in s["name"].lower():
                return s
        return None

    def search_text(self, query: str, limit: int = 20) -> list[dict]:
        q = query.lower()
        terms = [t for t in q.replace(",", " ").split() if len(t) > 2]
        results: list[tuple[float, dict, str]] = []

        def score(text: str) -> float:
            text_l = text.lower()
            s = 0.0
            for t in terms:
                if t in text_l:
                    s += 1.0 + (0.5 if text_l.count(t) > 1 else 0)
            return s

        collections = [
            ("service", self.services),
            ("commit", self.commits),
            ("pr", self.pull_requests),
            ("issue", self.issues),
            ("review", self.reviews),
            ("incident", self.incidents),
            ("deployment", self.deployments),
            ("rollback", self.rollbacks),
            ("outcome", self.outcomes),
            ("adr", self.architecture_decisions),
            ("memory", self.memory_entries),
        ]

        for kind, items in collections:
            for item in items:
                blob = json.dumps(item).lower()
                sc = score(blob)
                if sc > 0:
                    results.append((sc, item, kind))

        results.sort(key=lambda x: x[0], reverse=True)
        return [{"kind": k, "item": i, "score": sc} for sc, i, k in results[:limit]]

    def get_file_history(self, filename: str) -> list[dict]:
        base = filename.split("/")[-1]
        hits = self._commits_by_file.get(filename, []) + self._commits_by_file.get(base, [])
        seen: set[str] = set()
        out = []
        for c in hits:
            if c["id"] not in seen:
                seen.add(c["id"])
                out.append(c)
        out.sort(key=lambda x: x["date"], reverse=True)
        return out

    def find_similar_incidents(self, query: str, service_id: str | None = None, limit: int = 5) -> list[dict]:
        q = query.lower()
        terms = [t for t in q.replace(",", " ").split() if len(t) > 2]
        scored = []
        for inc in self.incidents:
            if service_id and inc["service_id"] != service_id:
                continue
            blob = f"{inc['title']} {inc['summary']} {inc['root_cause']} {inc['fix_summary']}".lower()
            sc = sum(1 for t in terms if t in blob)
            if sc > 0:
                scored.append((sc, inc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [i for _, i in scored[:limit]]

    def get_service_history(self, service_id: str) -> dict:
        return {
            "service": self.get(service_id),
            "commits": self._commits_by_service.get(service_id, [])[:12],
            "pull_requests": self._prs_by_service.get(service_id, [])[:12],
            "issues": self._issues_by_service.get(service_id, [])[:12],
            "reviews": self._reviews_by_service.get(service_id, [])[:12],
            "incidents": self._incidents_by_service.get(service_id, [])[:12],
            "deployments": self._deps_by_service.get(service_id, [])[:12],
            "rollbacks": self._rollbacks_by_service.get(service_id, [])[:8],
            "outcomes": self._outcomes_by_service.get(service_id, [])[:8],
            "adrs": self._adrs_by_service.get(service_id, [])[:8],
            "memory": self._mem_by_service.get(service_id, [])[:12],
        }

    def get_deployment_history(self, service_id: str | None = None, limit: int = 10) -> list[dict]:
        if service_id:
            return self._deps_by_service.get(service_id, [])[:limit]
        return sorted(self.deployments, key=lambda d: d["deployed_at"], reverse=True)[:limit]

    def get_issues(self, service_id: str | None = None, limit: int = 20) -> list[dict]:
        if service_id:
            return self._issues_by_service.get(service_id, [])[:limit]
        return sorted(self.issues, key=_time_key, reverse=True)[:limit]

    def get_reviews(self, pr_id: str | None = None, service_id: str | None = None, limit: int = 20) -> list[dict]:
        if pr_id:
            return self._reviews_by_pr.get(pr_id, [])[:limit]
        if service_id:
            return self._reviews_by_service.get(service_id, [])[:limit]
        return sorted(self.reviews, key=_time_key, reverse=True)[:limit]

    def get_rollbacks(self, service_id: str | None = None, limit: int = 15) -> list[dict]:
        if service_id:
            return self._rollbacks_by_service.get(service_id, [])[:limit]
        return sorted(self.rollbacks, key=_time_key, reverse=True)[:limit]

    def get_outcomes(self, service_id: str | None = None, limit: int = 15) -> list[dict]:
        if service_id:
            return self._outcomes_by_service.get(service_id, [])[:limit]
        return sorted(self.outcomes, key=_time_key, reverse=True)[:limit]

    def memory_stats(self) -> dict[str, int]:
        return {
            "services": len(self.services),
            "commits": len(self.commits),
            "pull_requests": len(self.pull_requests),
            "issues": len(self.issues),
            "reviews": len(self.reviews),
            "incidents": len(self.incidents),
            "deployments": len(self.deployments),
            "rollbacks": len(self.rollbacks),
            "outcomes": len(self.outcomes),
            "adrs": len(self.architecture_decisions),
            "memory_entries": len(self.memory_entries),
        }


store = EngineeringDataStore()
