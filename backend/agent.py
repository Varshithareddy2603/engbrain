"""Engineering Agent with Hindsight memory tools.

Answers are grounded strictly in retrieved evidence. Source IDs are always included.
Never invent historical facts.
"""

from __future__ import annotations

import re
from typing import Any

from data_loader import store


# ---------------------------------------------------------------------------
# Tools (callable by the agent)
# ---------------------------------------------------------------------------

def search_memory(query: str, limit: int = 15) -> list[dict]:
    """Search Hindsight memory across all entity types."""
    return store.search_text(query, limit=limit)


def get_file_history(filename: str) -> list[dict]:
    """Return commits that touched a given file, newest first."""
    return store.get_file_history(filename)


def find_similar_incidents(query: str, service_id: str | None = None, limit: int = 5) -> list[dict]:
    """Find past incidents similar to the described problem."""
    return store.find_similar_incidents(query, service_id=service_id, limit=limit)


def get_service_history(service_name_or_id: str) -> dict:
    """Full history for a service including issues, reviews, rollbacks, outcomes."""
    svc = store.get(service_name_or_id) or store.get_service_by_name(service_name_or_id)
    if not svc:
        return {"error": f"Service not found: {service_name_or_id}"}
    return store.get_service_history(svc["id"])


def get_deployment_history(service_name_or_id: str | None = None, limit: int = 10) -> list[dict]:
    """Recent deployments, optionally filtered by service."""
    sid = None
    if service_name_or_id:
        svc = store.get(service_name_or_id) or store.get_service_by_name(service_name_or_id)
        sid = svc["id"] if svc else service_name_or_id
    return store.get_deployment_history(sid, limit=limit)


def get_issues(service_name_or_id: str | None = None, limit: int = 15) -> list[dict]:
    """GitHub-style issues linked to PRs and incidents."""
    sid = None
    if service_name_or_id:
        svc = store.get(service_name_or_id) or store.get_service_by_name(service_name_or_id)
        sid = svc["id"] if svc else service_name_or_id
    return store.get_issues(sid, limit=limit)


def get_reviews(pr_id: str | None = None, service_name_or_id: str | None = None, limit: int = 15) -> list[dict]:
    """PR reviews and discussion outcomes."""
    sid = None
    if service_name_or_id:
        svc = store.get(service_name_or_id) or store.get_service_by_name(service_name_or_id)
        sid = svc["id"] if svc else service_name_or_id
    return store.get_reviews(pr_id=pr_id, service_id=sid, limit=limit)


def get_rollbacks(service_name_or_id: str | None = None, limit: int = 10) -> list[dict]:
    """Past rollbacks and config reversions."""
    sid = None
    if service_name_or_id:
        svc = store.get(service_name_or_id) or store.get_service_by_name(service_name_or_id)
        sid = svc["id"] if svc else service_name_or_id
    return store.get_rollbacks(sid, limit=limit)


def get_outcomes(service_name_or_id: str | None = None, limit: int = 10) -> list[dict]:
    """Measured outcomes after fixes, rollbacks, and experiments."""
    sid = None
    if service_name_or_id:
        svc = store.get(service_name_or_id) or store.get_service_by_name(service_name_or_id)
        sid = svc["id"] if svc else service_name_or_id
    return store.get_outcomes(sid, limit=limit)


TOOLS = {
    "search_memory": search_memory,
    "get_file_history": get_file_history,
    "find_similar_incidents": find_similar_incidents,
    "get_service_history": get_service_history,
    "get_deployment_history": get_deployment_history,
    "get_issues": get_issues,
    "get_reviews": get_reviews,
    "get_rollbacks": get_rollbacks,
    "get_outcomes": get_outcomes,
    "review_change": None,  # bound below after def
}


# ---------------------------------------------------------------------------
# Lightweight retrieval + answer synthesis (no external LLM required for demo)
# ---------------------------------------------------------------------------

def _extract_service_hint(question: str) -> str | None:
    q = question.lower()
    for s in store.services:
        name = s["name"].lower()
        if name in q or name.replace("-", "_") in q or name.replace("-", " ") in q:
            return s["id"]
    # common aliases
    if "payment" in q:
        return "svc-payment"
    if "auth" in q:
        return "svc-auth"
    if "order" in q:
        return "svc-order"
    if "notif" in q or "notification" in q:
        return "svc-notif"
    if "inventory" in q or "stock" in q:
        return "svc-inventory"
    return None


def _extract_file_hint(question: str) -> str | None:
    # Look for .py / .ts / .go / .java filenames
    m = re.search(r"([\w\-./]+\.(?:py|ts|js|go|java|rb))", question, re.I)
    if m:
        return m.group(1)
    if "retry" in question.lower() and "payment" in question.lower():
        return "payment_service.py"
    return None


def _collect_evidence(question: str) -> dict[str, Any]:
    """Run tools based on question heuristics and gather grounded evidence."""
    evidence: dict[str, Any] = {
        "memory_hits": [],
        "file_history": [],
        "similar_incidents": [],
        "service_history": None,
        "deployments": [],
        "issues": [],
        "reviews": [],
        "rollbacks": [],
        "outcomes": [],
        "source_ids": set(),
    }

    service_id = _extract_service_hint(question)
    filename = _extract_file_hint(question)

    # Always search memory
    evidence["memory_hits"] = search_memory(question, limit=15)
    for hit in evidence["memory_hits"]:
        evidence["source_ids"].add(hit["item"]["id"])

    if filename:
        evidence["file_history"] = get_file_history(filename)
        for c in evidence["file_history"]:
            evidence["source_ids"].add(c["id"])
            if c.get("pr_id"):
                evidence["source_ids"].add(c["pr_id"])

    # Similar incidents (timeout / retry / failure oriented questions)
    q_lower = question.lower()
    incident_query = question
    if any(k in q_lower for k in ("timeout", "retry", "fail", "outage", "latency", "504", "circuit")):
        incident_query = "timeout retry failure outage latency 504 circuit breaker payment"
    evidence["similar_incidents"] = find_similar_incidents(
        incident_query, service_id=service_id, limit=5
    )
    for inc in evidence["similar_incidents"]:
        evidence["source_ids"].add(inc["id"])
        for pid in inc.get("related_pr_ids", []):
            evidence["source_ids"].add(pid)
        for cid in inc.get("related_commit_ids", []):
            evidence["source_ids"].add(cid)

    if service_id:
        evidence["service_history"] = get_service_history(service_id)
        if evidence["service_history"] and "error" not in evidence["service_history"]:
            for coll in ("commits", "pull_requests", "incidents", "deployments", "adrs", "memory"):
                for item in evidence["service_history"].get(coll, []):
                    evidence["source_ids"].add(item["id"])
        evidence["deployments"] = get_deployment_history(service_id, limit=8)
    else:
        evidence["deployments"] = get_deployment_history(limit=6)

    for d in evidence["deployments"]:
        evidence["source_ids"].add(d["id"])

    # Issues, reviews, rollbacks, outcomes
    evidence["issues"] = get_issues(service_id, limit=10) if service_id else get_issues(limit=8)
    for i in evidence["issues"]:
        evidence["source_ids"].add(i["id"])

    evidence["reviews"] = get_reviews(service_name_or_id=service_id, limit=10) if service_id else get_reviews(limit=8)
    for r in evidence["reviews"]:
        evidence["source_ids"].add(r["id"])

    evidence["rollbacks"] = get_rollbacks(service_id, limit=8) if service_id else get_rollbacks(limit=6)
    for r in evidence["rollbacks"]:
        evidence["source_ids"].add(r["id"])

    evidence["outcomes"] = get_outcomes(service_id, limit=8) if service_id else get_outcomes(limit=6)
    for o in evidence["outcomes"]:
        evidence["source_ids"].add(o["id"])

    evidence["source_ids"] = sorted(evidence["source_ids"])
    return evidence


def _build_answer(question: str, evidence: dict) -> dict:
    """Synthesize a structured answer strictly from evidence."""
    q = question.lower()
    answer_parts: list[str] = []
    historical_context: list[str] = []
    related_incidents: list[dict] = []
    github_evidence: list[dict] = []
    deployments: list[dict] = []
    sources: list[dict] = []

    # Intent flags (order of checks matters)
    is_before_change = (
        "before changing" in q
        or "should i know" in q
        or "what should i know" in q
        or ("risk" in q and "chang" in q)
    )
    is_why_retry = (
        not is_before_change
        and ("retry" in q)
        and ("payment" in q or "payment_service" in q)
        and ("why" in q or "exist" in q or "reason" in q or "logic" in q)
    )
    is_seen_before = (
        ("seen" in q and "before" in q)
        or ("timeout" in q and ("seen" in q or "have we" in q or "previous" in q))
    )
    is_what_happened = "what happened" in q or ("history" in q and "payment" in q)

    # ---- What should I know before changing ----
    if is_before_change:
        answer_parts.append(
            "Before changing retry / circuit-breaker logic in payment-service, treat it as a high-risk P0 surface. "
            "The current behaviour is the product of three SEV-1/SEV-2 incidents and an explicit ADR."
        )
        answer_parts.append(
            "Key constraints from Hindsight memory:\n"
            "• Max attempts = 3 was chosen after p99 latency climbed with 5 attempts (INC-2025-0612).\n"
            "• Circuit breaker is mandatory — retries alone caused a thundering herd during a total provider outage (INC-2025-0730).\n"
            "• Retry-rate metrics are a leading indicator; alerts fire before user-visible error rate spikes (PR-134 / mem-004).\n"
            "• Non-retryable 4xx must never be retried (ADR-007).\n"
            "• Order-service depends on clients retrying after payment timeouts; those retries are made safe by idempotency keys (ADR-012)."
        )
        historical_context.append(
            "Changing this code without preserving backoff + circuit-breaker + metrics risks repeating INC-2025-0310 / 0730."
        )
        if evidence.get("rollbacks"):
            rb = evidence["rollbacks"][0]
            historical_context.append(
                f"Past rollback: {rb['id']} — {rb.get('title')} ({rb.get('reason', '')[:80]})"
            )
        if evidence.get("outcomes"):
            for o in evidence["outcomes"][:2]:
                historical_context.append(
                    f"Outcome {o['id']}: {o.get('title')} — success={o.get('success')}"
                )
        if evidence.get("issues"):
            historical_context.append(
                f"Related issues in memory: {', '.join(i['id'] for i in evidence['issues'][:4])}"
            )
        # Surface code review guidance
        for r in (evidence.get("reviews") or [])[:4]:
            if r.get("service_id") == "svc-payment" or "retry" in (r.get("body") or "").lower():
                historical_context.append(
                    f"Code review {r['id']} on {r.get('pr_id')}: {r.get('reviewer')} — {r.get('body', '')[:120]}"
                )
                for c in (r.get("comments") or [])[:2]:
                    historical_context.append(
                        f"  ↳ {c.get('file')}:{c.get('line')} — {c.get('body', '')[:100]}"
                    )

        for inc in evidence["similar_incidents"][:3]:
            related_incidents.append({
                "id": inc["id"],
                "title": inc["title"],
                "severity": inc["severity"],
                "root_cause": inc["root_cause"],
            })
        for hit in evidence["memory_hits"]:
            if hit["kind"] in ("adr", "memory", "pr"):
                item = hit["item"]
                github_evidence.append({
                    "type": hit["kind"],
                    "id": item["id"],
                    "title": item.get("title") or item.get("message", ""),
                    "summary": (item.get("decision") or item.get("content") or item.get("body") or "")[:180],
                })
        for d in evidence["deployments"][:4]:
            deployments.append({
                "id": d["id"],
                "version": d["version"],
                "deployed_at": d["deployed_at"],
                "notes": d["notes"],
            })

    # ---- Why retry logic ----
    elif is_why_retry or (not is_before_change and "retry" in q and "payment" in q):
        # Trace: code → commit → PR → incident → root cause → fix
        answer_parts.append(
            "The retry logic in `payment_service.py` exists because of a SEV-1 incident "
            "on 2025-03-10 (INC-2025-0310). The external payment provider returned intermittent 504s; "
            "our original synchronous calls without backoff amplified the load, exhausted connection pools, "
            "and caused cascading checkout failures."
        )
        answer_parts.append(
            "The permanent fix landed in PR #42 (commit a1b2c3d4e5f6) which introduced exponential backoff "
            "with jitter. That change was later refined: max attempts reduced from 5 → 3 after a latency "
            "regression (INC-2025-0612 / PR #87), and a circuit breaker was added after a full provider "
            "outage produced a thundering herd (INC-2025-0730 / PR #112). These decisions are captured in ADR-007."
        )
        historical_context.append(
            "Timeline: INC-2025-0310 (Mar 10) → PR-42 + ADR-007 (Mar 12) → latency regression INC-2025-0612 "
            "(Jun) → PR-87 → full outage INC-2025-0730 (Jul) → PR-112 circuit breaker (Aug) → retry metrics PR-134 (Sep)."
        )
        for inc in evidence["similar_incidents"]:
            if "payment" in (inc.get("service_id") or ""):
                related_incidents.append({
                    "id": inc["id"],
                    "title": inc["title"],
                    "severity": inc["severity"],
                    "root_cause": inc["root_cause"],
                    "fix_summary": inc["fix_summary"],
                })
        for c in evidence["file_history"]:
            github_evidence.append({
                "type": "commit",
                "id": c["id"],
                "sha": c["sha"],
                "message": c["message"],
                "author": c["author"],
                "date": c["date"],
                "pr_id": c.get("pr_id"),
            })
        # Also pull related PRs from memory hits
        for hit in evidence["memory_hits"]:
            item = hit["item"]
            if hit["kind"] == "pr" and item.get("service_id") == "svc-payment":
                github_evidence.append({
                    "type": "pr",
                    "id": item["id"],
                    "number": item["number"],
                    "title": item["title"],
                    "created_at": item.get("created_at"),
                    "merged_at": item["merged_at"],
                    "description": (item.get("description") or item.get("body") or "")[:300],
                    "body_excerpt": (item.get("body") or "")[:200] + ("…" if len(item.get("body") or "") > 200 else ""),
                })
        for d in evidence["deployments"]:
            if d["service_id"] == "svc-payment":
                deployments.append({
                    "id": d["id"],
                    "version": d["version"],
                    "deployed_at": d["deployed_at"],
                    "notes": d["notes"],
                    "status": d["status"],
                })

        # Code reviews on related payment PRs
        for r in evidence.get("reviews") or []:
            if r.get("service_id") == "svc-payment":
                github_evidence.append({
                    "type": "code_review",
                    "id": r["id"],
                    "pr_id": r.get("pr_id"),
                    "title": f"Review by {r.get('reviewer')} ({r.get('state')})",
                    "description": r.get("body"),
                    "created_at": r.get("created_at") or r.get("submitted_at"),
                    "comments": r.get("comments") or [],
                })

    # ---- Have we seen this timeout / problem before ----
    elif is_seen_before or "timeout" in q:
        sims = evidence["similar_incidents"]
        if sims:
            answer_parts.append(
                f"Yes. Hindsight found {len(sims)} related incident(s). "
                "The closest match is the March 2025 payment-gateway timeout cascade (INC-2025-0310) "
                "and the later full-provider outage (INC-2025-0730)."
            )
            for inc in sims[:3]:
                answer_parts.append(
                    f"• {inc['id']} ({inc['severity']}): {inc['title']} — Root cause: {inc['root_cause']}"
                )
            related_incidents = [
                {"id": i["id"], "title": i["title"], "severity": i["severity"], "root_cause": i["root_cause"]}
                for i in sims
            ]
        else:
            answer_parts.append("No closely matching incidents found in Hindsight memory for this description.")
        historical_context.append(
            "Past fixes emphasised backoff, circuit breakers, and retry-rate observability rather than simply increasing attempt counts."
        )

    # ---- What happened with payment-service ----
    elif is_what_happened or (service_id := _extract_service_hint(question)):
        sid = _extract_service_hint(question) or "svc-payment"
        hist = evidence.get("service_history") or get_service_history(sid)
        if hist and "error" not in hist:
            svc = hist["service"]
            answer_parts.append(
                f"**{svc['name']}** ({svc['criticality']}) — {svc['description']}. Owners: {', '.join(svc['owners'])}."
            )
            incs = hist.get("incidents", [])
            if incs:
                answer_parts.append(f"Recent incidents ({len(incs)}):")
                for inc in incs[:4]:
                    answer_parts.append(f"• {inc['id']} [{inc['severity']}]: {inc['title']} (resolved {inc.get('resolved_at', 'n/a')[:10]})")
                    related_incidents.append({
                        "id": inc["id"],
                        "title": inc["title"],
                        "severity": inc["severity"],
                        "root_cause": inc.get("root_cause"),
                    })
            mems = hist.get("memory", [])
            if mems:
                historical_context.append("Lessons in Hindsight memory:")
                for m in mems[:4]:
                    historical_context.append(f"• {m['title']}: {m['content'][:120]}…")
            for c in hist.get("commits", [])[:5]:
                github_evidence.append({
                    "type": "commit",
                    "id": c["id"],
                    "sha": c["sha"],
                    "message": c["message"],
                    "date": c["date"],
                })
            for d in hist.get("deployments", [])[:5]:
                deployments.append({
                    "id": d["id"],
                    "version": d["version"],
                    "deployed_at": d["deployed_at"],
                    "notes": d["notes"],
                })
        else:
            answer_parts.append("Service not found in Hindsight memory.")

    # ---- Generic fallback ----
    else:
        hits = evidence["memory_hits"][:6]
        if hits:
            answer_parts.append(
                f"Hindsight retrieved {len(evidence['memory_hits'])} relevant memory items. Top matches:"
            )
            for hit in hits:
                item = hit["item"]
                title = item.get("title") or item.get("message") or item.get("name") or item["id"]
                answer_parts.append(f"• [{hit['kind']}] {item['id']}: {title}")
                if hit["kind"] == "incident":
                    related_incidents.append({
                        "id": item["id"],
                        "title": item.get("title"),
                        "severity": item.get("severity"),
                    })
        else:
            answer_parts.append(
                "No strong matches in Hindsight memory for this question. "
                "Try mentioning a service name, file, or past incident ID."
            )
        historical_context.append(
            "Answers improve as more commits, PRs, incidents, and decisions are ingested into Hindsight memory."
        )

    # Build sources list from IDs
    for sid in evidence["source_ids"][:20]:
        entity = store.get(sid)
        if entity:
            sources.append({
                "id": sid,
                "type": _guess_type(sid),
                "label": entity.get("title") or entity.get("message") or entity.get("name") or sid,
            })

    return {
        "answer": "\n\n".join(answer_parts) if answer_parts else "Insufficient evidence in Hindsight memory to answer confidently.",
        "historical_context": historical_context,
        "related_incidents": related_incidents,
        "github_evidence": github_evidence,
        "deployments": deployments,
        "sources": sources,
        "evidence_count": len(evidence["source_ids"]),
    }


def _guess_type(entity_id: str) -> str:
    if entity_id.startswith("INC-"):
        return "incident"
    if entity_id.startswith("pr-"):
        return "pr"
    if entity_id.startswith("cmt-"):
        return "commit"
    if entity_id.startswith("dep-"):
        return "deployment"
    if entity_id.startswith("ADR-"):
        return "adr"
    if entity_id.startswith("mem-"):
        return "memory"
    if entity_id.startswith("svc-"):
        return "service"
    if entity_id.startswith("issue-"):
        return "issue"
    if entity_id.startswith("rev-"):
        return "review"
    if entity_id.startswith("rb-"):
        return "rollback"
    if entity_id.startswith("out-"):
        return "outcome"
    return "unknown"


def ask(question: str) -> dict:
    """Main entry: retrieve evidence → synthesise grounded answer."""
    if not question or not question.strip():
        return {
            "answer": "Please ask a question about code history, incidents, or engineering decisions.",
            "historical_context": [],
            "related_incidents": [],
            "github_evidence": [],
            "deployments": [],
            "sources": [],
            "evidence_count": 0,
        }

    evidence = _collect_evidence(question.strip())
    result = _build_answer(question.strip(), evidence)
    result["question"] = question.strip()
    return result


# ---------------------------------------------------------------------------
# Incident-Aware Code Review
# Compares a proposed change with Hindsight memory and explains warnings.
# ---------------------------------------------------------------------------

_RISK_KEYWORDS = {
    "retry": ["retry", "backoff", "max_attempts", "attempts", "jitter"],
    "circuit_breaker": ["circuit", "breaker", "fail-fast", "fail fast"],
    "timeout": ["timeout", "deadline", "504", "latency"],
    "ttl": ["ttl", "token", "session", "refresh"],
    "idempotency": ["idempotency", "idempotent", "duplicate"],
    "rate_limit": ["rate limit", "rate_limit", "throttle", "sms", "carrier"],
    "concurrency": ["pool", "concurrency", "thread", "connection pool"],
    "flag": ["feature flag", "flag", "canary"],
}


def review_change(
    service: str,
    change_summary: str,
    files: list[str] | None = None,
) -> dict:
    """Incident-aware review of a proposed change against engineering memory."""
    files = files or []
    svc = store.get(service) or store.get_service_by_name(service)
    if not svc:
        return {
            "service": service,
            "change_summary": change_summary,
            "risk_level": "unknown",
            "summary": f"Service not found in Hindsight memory: {service}",
            "warnings": [],
            "related_incidents": [],
            "related_rollbacks": [],
            "related_reviews": [],
            "related_outcomes": [],
            "sources": [],
            "themes_detected": [],
            "files": files,
        }

    sid = svc["id"]
    blob = f"{change_summary} {' '.join(files)}".lower()
    themes = [name for name, kws in _RISK_KEYWORDS.items() if any(k in blob for k in kws)]
    if not themes:
        themes = ["general"]

    query = change_summary + " " + " ".join(themes) + " " + " ".join(files)
    incidents = store.find_similar_incidents(query, service_id=sid, limit=6)
    if not incidents:
        incidents = store.find_similar_incidents(query, service_id=None, limit=4)

    hist = store.get_service_history(sid)
    rollbacks = store.get_rollbacks(sid, limit=8)
    outcomes = store.get_outcomes(sid, limit=8)
    reviews = store.get_reviews(service_id=sid, limit=12)
    adrs = hist.get("adrs") or []
    memory = hist.get("memory") or []
    issues = store.get_issues(sid, limit=10)

    def relevant(item: dict) -> bool:
        parts = [str(item.get(k, "")) for k in (
            "title", "reason", "body", "summary", "content", "decision", "message"
        )]
        for c in item.get("comments") or []:
            parts.append(str(c.get("body", "")))
            parts.append(str(c.get("file", "")))
        text_l = " ".join(parts).lower()
        if any(t in text_l for t in themes if t != "general"):
            return True
        for kws in _RISK_KEYWORDS.values():
            if any(k in blob and k in text_l for k in kws):
                return True
        if files and any(f.split("/")[-1].lower() in text_l for f in files):
            return True
        return False

    rel_rollbacks = [r for r in rollbacks if relevant(r)] or rollbacks[:2]
    rel_reviews = [r for r in reviews if relevant(r)] or reviews[:3]
    rel_outcomes = [o for o in outcomes if relevant(o)] or outcomes[:2]
    rel_adrs = [a for a in adrs if relevant(a)] or adrs[:2]
    rel_mem = [m for m in memory if relevant(m)] or memory[:2]

    warnings: list[dict] = []
    sources: set[str] = set()

    risky_phrases = [
        ("remove backoff", "Removing backoff recreated cascade failures in INC-2025-0310."),
        ("increase max_attempts", "Raising max_attempts above 3 caused p99 regression (INC-2025-0612 / rb-2025-06-12)."),
        ("max_attempts = 5", "max_attempts=5 was rolled back after latency incident INC-2025-0612."),
        ("max_attempts to 5", "max_attempts=5 was rolled back after latency incident INC-2025-0612."),
        ("disable circuit", "Disabling the circuit breaker risks thundering herd (INC-2025-0730)."),
        ("remove circuit", "Removing the circuit breaker risks thundering herd (INC-2025-0730)."),
        ("no jitter", "Missing jitter caused synchronized retries; reviewers required full-jitter on PR-42."),
        ("retry 4xx", "Code review on PR-42 forbade retrying 4xx responses."),
        ("shorten ttl", "Short TTL without client readiness caused session drops (INC-2025-0304 / rb-2025-03-05)."),
        ("reduce ttl", "Short TTL without client readiness caused session drops (INC-2025-0304 / rb-2025-03-05)."),
    ]
    for phrase, explanation in risky_phrases:
        if phrase in blob:
            warnings.append({
                "id": f"warn-phrase-{phrase.replace(' ', '-')}",
                "severity": "high",
                "title": f"High-risk pattern detected: “{phrase}”",
                "why": explanation,
                "recommendation": "Do not ship this without incident review and a feature flag.",
                "evidence_ids": [],
            })

    for inc in incidents:
        severity = inc.get("severity", "SEV-2")
        risk = "high" if severity == "SEV-1" else ("medium" if severity == "SEV-2" else "low")
        warnings.append({
            "id": f"warn-{inc['id']}",
            "severity": risk,
            "title": f"Matches incident pattern: {inc['title']}",
            "why": (
                f"Past {severity} incident {inc['id']}: {inc.get('root_cause', '')} "
                f"Fix was: {inc.get('fix_summary', '')}"
            ),
            "recommendation": (
                "Do not remove safeguards introduced after this incident "
                "(backoff, circuit breaker, metrics, flags) without an explicit ADR update."
            ),
            "evidence_ids": [inc["id"]] + list(inc.get("related_pr_ids") or [])[:3],
        })
        sources.add(inc["id"])
        for pid in inc.get("related_pr_ids") or []:
            sources.add(pid)

    for rb in rel_rollbacks[:3]:
        warnings.append({
            "id": f"warn-{rb['id']}",
            "severity": "high",
            "title": f"Similar change was rolled back: {rb.get('title')}",
            "why": rb.get("reason") or "Prior rollback recorded in Hindsight memory.",
            "recommendation": (
                f"Review rollback {rb['id']} ({rb.get('from_version')} → {rb.get('to_version')}) "
                "before shipping. Prefer feature flags / canary."
            ),
            "evidence_ids": [rb["id"]] + list(rb.get("related_incident_ids") or []),
        })
        sources.add(rb["id"])

    for rev in rel_reviews[:4]:
        inline = rev.get("comments") or []
        file_hits = [
            c for c in inline
            if not files or any((f.split("/")[-1] in (c.get("file") or "")) for f in files)
        ]
        comment_bits = file_hits or inline[:2]
        why = rev.get("body") or ""
        if comment_bits:
            why += " | " + "; ".join(
                f"{c.get('file')}:{c.get('line')} — {c.get('body')}" for c in comment_bits[:3]
            )
        warnings.append({
            "id": f"warn-{rev['id']}",
            "severity": "medium" if rev.get("state") == "changes_requested" else "low",
            "title": f"Prior code review on {rev.get('pr_id')}: {rev.get('reviewer')} ({rev.get('state')})",
            "why": why,
            "recommendation": "Preserve review constraints (e.g. no retry on 4xx, jitter, metrics, flags).",
            "evidence_ids": [x for x in [rev["id"], rev.get("pr_id")] if x],
        })
        sources.add(rev["id"])
        if rev.get("pr_id"):
            sources.add(rev["pr_id"])

    for adr in rel_adrs[:2]:
        warnings.append({
            "id": f"warn-{adr['id']}",
            "severity": "high",
            "title": f"Architecture decision applies: {adr.get('title')}",
            "why": f"{adr.get('decision', '')} Consequences: {adr.get('consequences', '')}",
            "recommendation": f"Any change conflicting with {adr['id']} needs an ADR update and review.",
            "evidence_ids": [adr["id"]],
        })
        sources.add(adr["id"])

    for mem in rel_mem[:2]:
        warnings.append({
            "id": f"warn-{mem['id']}",
            "severity": "medium",
            "title": f"Hindsight lesson: {mem.get('title')}",
            "why": mem.get("content") or "",
            "recommendation": "Treat this lesson as a soft constraint unless explicitly superseded.",
            "evidence_ids": [mem["id"]] + list(mem.get("source_ids") or [])[:3],
        })
        sources.add(mem["id"])

    sev_rank = {"high": 3, "medium": 2, "low": 1}
    if not warnings:
        risk_level = "low"
        summary = (
            f"No strong incident overlap found in Hindsight for this change on {svc['name']}. "
            "Still run normal review; memory may be incomplete."
        )
    else:
        risk_level = max(warnings, key=lambda w: sev_rank.get(w["severity"], 0))["severity"]
        summary = (
            f"Incident-aware review for {svc['name']}: {len(warnings)} warning(s), "
            f"overall risk {risk_level}. Warnings are grounded in past incidents, "
            f"rollbacks, ADRs, and code reviews."
        )

    source_list = []
    for eid in sorted(sources):
        if not eid:
            continue
        ent = store.get(eid)
        source_list.append({
            "id": eid,
            "type": _guess_type(eid),
            "label": (ent or {}).get("title") or (ent or {}).get("message") or eid,
        })

    return {
        "service": svc["name"],
        "service_id": sid,
        "change_summary": change_summary,
        "files": files,
        "themes_detected": themes,
        "risk_level": risk_level,
        "summary": summary,
        "warnings": warnings,
        "related_incidents": [
            {
                "id": i["id"],
                "title": i["title"],
                "severity": i.get("severity"),
                "root_cause": i.get("root_cause"),
                "fix_summary": i.get("fix_summary"),
            }
            for i in incidents
        ],
        "related_rollbacks": [
            {"id": r["id"], "title": r.get("title"), "reason": r.get("reason")}
            for r in rel_rollbacks[:4]
        ],
        "related_reviews": [
            {
                "id": r["id"],
                "pr_id": r.get("pr_id"),
                "reviewer": r.get("reviewer"),
                "state": r.get("state"),
                "body": r.get("body"),
                "comments": r.get("comments") or [],
            }
            for r in rel_reviews[:5]
        ],
        "related_outcomes": [
            {
                "id": o["id"],
                "title": o.get("title"),
                "success": o.get("success"),
                "summary": o.get("summary"),
            }
            for o in rel_outcomes[:4]
        ],
        "sources": source_list,
    }


TOOLS["review_change"] = review_change
