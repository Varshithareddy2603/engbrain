const API = "";

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`view-${btn.dataset.view}`).classList.add("active");
  });
});

function goToAsk(question) {
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelector('[data-view="ask"]').classList.add("active");
  document.getElementById("view-ask").classList.add("active");
  document.getElementById("question-input").value = question;
  runAsk();
}

// Demo buttons
document.querySelectorAll(".demo-btn").forEach((btn) => {
  btn.addEventListener("click", () => goToAsk(btn.dataset.q));
});

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
async function loadDashboard() {
  const health = await fetch(`${API}/api/health`).then((r) => r.json());
  const stats = health.memory_stats;
  const grid = document.getElementById("stats-grid");
  const labels = {
    services: "Services",
    commits: "Commits",
    pull_requests: "Pull Requests",
    issues: "Issues",
    reviews: "Reviews",
    incidents: "Incidents",
    deployments: "Deployments",
    rollbacks: "Rollbacks",
    outcomes: "Outcomes",
    adrs: "ADRs",
    memory_entries: "Memory Lessons",
  };
  grid.innerHTML = Object.entries(stats)
    .map(
      ([k, v]) => `
    <div class="stat-card">
      <div class="value">${v}</div>
      <div class="label">${labels[k] || k}</div>
    </div>`
    )
    .join("");

  const services = await fetch(`${API}/api/services`).then((r) => r.json());
  document.getElementById("services-list").innerHTML = services
    .map(
      (s) => `
    <div class="entity-item">
      <div class="name">${s.name} <span class="badge badge-${s.criticality.toLowerCase()}">${s.criticality}</span></div>
      <div class="meta">${s.description} · ${s.language} · ${s.owners.join(", ")}</div>
    </div>`
    )
    .join("");

  const memory = await fetch(`${API}/api/memory`).then((r) => r.json());
  document.getElementById("memory-list").innerHTML = memory
    .slice(0, 5)
    .map(
      (m) => `
    <div class="entity-item">
      <div class="name">${m.title}</div>
      <div class="meta">${m.content.slice(0, 110)}…</div>
    </div>`
    )
    .join("");
}

// ---------------------------------------------------------------------------
// Ask
// ---------------------------------------------------------------------------
document.getElementById("ask-btn").addEventListener("click", runAsk);
document.getElementById("question-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runAsk();
});

async function runAsk() {
  const question = document.getElementById("question-input").value.trim();
  if (!question) return;

  const btn = document.getElementById("ask-btn");
  const status = document.getElementById("ask-status");
  btn.disabled = true;
  status.textContent = "Searching Hindsight memory…";

  try {
    const res = await fetch(`${API}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    renderAnswer(data);
    status.textContent = `Grounded on ${data.evidence_count} source(s)`;
  } catch (err) {
    status.textContent = "Error: " + err.message;
  } finally {
    btn.disabled = false;
  }
}

function renderAnswer(data) {
  const panel = document.getElementById("answer-panel");
  panel.classList.remove("hidden");

  document.getElementById("answer-text").textContent = data.answer;

  const ctx = document.getElementById("historical-context");
  ctx.innerHTML =
    (data.historical_context || [])
      .map((c) => `<li>${escapeHtml(c)}</li>`)
      .join("") || "<li>None</li>";

  const incs = document.getElementById("related-incidents");
  if (data.related_incidents && data.related_incidents.length) {
    incs.innerHTML = data.related_incidents
      .map(
        (i) => `
      <div class="mini-card">
        <div class="id">${i.id} ${i.severity ? `<span class="badge badge-${(i.severity || "").toLowerCase().replace("-", "")}">${i.severity}</span>` : ""}</div>
        <div class="title">${escapeHtml(i.title || "")}</div>
        ${i.root_cause ? `<div class="detail">Root cause: ${escapeHtml(i.root_cause)}</div>` : ""}
        ${i.fix_summary ? `<div class="detail">Fix: ${escapeHtml(i.fix_summary)}</div>` : ""}
      </div>`
      )
      .join("");
  } else {
    incs.innerHTML = '<div class="mini-card"><div class="detail">No related incidents retrieved</div></div>';
  }

  const gh = document.getElementById("github-evidence");
  if (data.github_evidence && data.github_evidence.length) {
    gh.innerHTML = data.github_evidence
      .map(
        (g) => {
          const comments = (g.comments || [])
            .map((c) => `<div class="detail">↳ <code>${escapeHtml(String(c.file || ""))}:${c.line ?? ""}</code> — ${escapeHtml((c.body || "").slice(0, 140))}</div>`)
            .join("");
          return `
      <div class="mini-card">
        <div class="id">${(g.type || "ITEM").toUpperCase()} · ${g.id}${g.sha ? ` · ${g.sha.slice(0, 8)}` : ""}${g.number ? ` · #${g.number}` : ""}${g.pr_id ? ` · ${g.pr_id}` : ""}</div>
        <div class="title">${escapeHtml(g.title || g.message || "")}</div>
        ${g.description || g.summary || g.body_excerpt ? `<div class="detail">${escapeHtml((g.description || g.summary || g.body_excerpt || "").slice(0, 200))}</div>` : ""}
        ${comments}
        ${g.created_at ? `<div class="detail">Created: ${g.created_at}</div>` : ""}
        ${g.date || g.merged_at ? `<div class="detail">${g.merged_at ? "Merged: " + g.merged_at : g.date}</div>` : ""}
      </div>`;
        }
      )
      .join("");
  } else {
    gh.innerHTML = '<div class="mini-card"><div class="detail">No GitHub evidence for this query</div></div>';
  }

  const deps = document.getElementById("deployments-list");
  if (data.deployments && data.deployments.length) {
    deps.innerHTML = data.deployments
      .map(
        (d) => `
      <div class="mini-card">
        <div class="id">${d.id} · ${d.version || ""}</div>
        <div class="title">${d.deployed_at || ""}</div>
        ${d.notes ? `<div class="detail">${escapeHtml(d.notes)}</div>` : ""}
      </div>`
      )
      .join("");
  } else {
    deps.innerHTML = '<div class="mini-card"><div class="detail">No deployments linked</div></div>';
  }

  document.getElementById("evidence-count").textContent = data.evidence_count || 0;
  const sources = document.getElementById("sources-list");
  sources.innerHTML = (data.sources || [])
    .map(
      (s) =>
        `<span class="source-chip"><span class="type">${s.type}</span>${s.id}</span>`
    )
    .join("");
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------
async function loadTimeline() {
  const events = await fetch(`${API}/api/timeline`).then((r) => r.json());
  const el = document.getElementById("timeline");
  el.innerHTML = events
    .map((e) => {
      const time = (e.time || "").replace("T", " ").slice(0, 16);
      let meta = e.service_id || "";
      if (e.severity) meta += ` · ${e.severity}`;
      if (e.number) meta += ` · PR #${e.number}`;
      if (e.status) meta += ` · ${e.status}`;
      if (e.notes) meta += ` · ${e.notes.slice(0, 60)}`;
      return `
      <div class="tl-item type-${e.type}">
        <div class="tl-time">${time}</div>
        <div class="tl-title">${escapeHtml(e.title)}</div>
        <div class="tl-meta">${e.type.toUpperCase()} · ${escapeHtml(meta)}</div>
      </div>`;
    })
    .join("");
}

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------
async function loadIncidents() {
  const incidents = await fetch(`${API}/api/incidents`).then((r) => r.json());
  const el = document.getElementById("incidents-list");
  el.innerHTML = incidents
    .map(
      (i) => `
    <div class="inc-card" data-id="${i.id}">
      <div class="row">
        <span class="badge badge-${(i.severity || "").toLowerCase().replace("-", "")}">${i.severity}</span>
        <span class="title">${escapeHtml(i.title)}</span>
        <span class="meta" style="color:var(--text-muted);font-size:0.8rem">${i.id}</span>
      </div>
      <div class="summary">${escapeHtml(i.summary.slice(0, 180))}…</div>
    </div>`
    )
    .join("");

  el.querySelectorAll(".inc-card").forEach((card) => {
    card.addEventListener("click", () => showIncident(card.dataset.id));
  });
}

async function showIncident(id) {
  const data = await fetch(`${API}/api/incidents/${id}`).then((r) => r.json());
  const inc = data.incident;
  const rel = data.related;
  const detail = document.getElementById("incident-detail");
  detail.classList.remove("hidden");
  detail.innerHTML = `
    <button class="close-detail" onclick="this.parentElement.classList.add('hidden')">Close</button>
    <h2>${escapeHtml(inc.title)}</h2>
    <div class="row" style="gap:0.5rem;margin:0.4rem 0">
      <span class="badge badge-${(inc.severity || "").toLowerCase().replace("-", "")}">${inc.severity}</span>
      <span style="font-family:var(--mono);font-size:0.8rem;color:var(--text-muted)">${inc.id}</span>
      <span style="font-size:0.8rem;color:var(--text-muted)">${inc.started_at?.slice(0, 10)} → ${inc.resolved_at?.slice(0, 10) || "open"}</span>
    </div>
    <p style="margin:0.75rem 0;font-size:0.92rem">${escapeHtml(inc.summary)}</p>
    <div class="detail-grid">
      <div class="detail-block">
        <h4>Root Cause</h4>
        <p>${escapeHtml(inc.root_cause)}</p>
      </div>
      <div class="detail-block">
        <h4>Fix Summary</h4>
        <p>${escapeHtml(inc.fix_summary)}</p>
      </div>
      <div class="detail-block">
        <h4>Related PRs</h4>
        <ul>${(rel.prs || []).map((p) => `<li>#${p.number} — ${escapeHtml(p.title)}</li>`).join("") || "<li>None</li>"}</ul>
      </div>
      <div class="detail-block">
        <h4>Related Commits</h4>
        <ul>${(rel.commits || []).map((c) => `<li><code>${c.sha.slice(0, 8)}</code> ${escapeHtml(c.message)}</li>`).join("") || "<li>None</li>"}</ul>
      </div>
    </div>
    ${
      inc.timeline && inc.timeline.length
        ? `<div class="detail-block" style="margin-top:1rem"><h4>Timeline</h4><ul>${inc.timeline
            .map((t) => `<li><code>${t.time.slice(0, 16)}</code> ${escapeHtml(t.event)}</li>`)
            .join("")}</ul></div>`
        : ""
    }
  `;
  detail.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
loadDashboard();
loadTimeline();
loadIncidents();

// ---------------------------------------------------------------------------
// Incident-Aware Code Review
// ---------------------------------------------------------------------------
let selectedReviewService = "payment-service";

document.querySelectorAll("#review-services .pill").forEach((pill) => {
  pill.addEventListener("click", () => {
    document.querySelectorAll("#review-services .pill").forEach((p) => p.classList.remove("active"));
    pill.classList.add("active");
    selectedReviewService = pill.dataset.svc;
  });
});

document.querySelectorAll("[data-review]").forEach((btn) => {
  btn.addEventListener("click", () => {
    try {
      const spec = JSON.parse(btn.dataset.review);
      selectedReviewService = spec.service;
      document.querySelectorAll("#review-services .pill").forEach((p) => {
        p.classList.toggle("active", p.dataset.svc === spec.service);
      });
      document.getElementById("review-change-input").value = spec.change || "";
      document.getElementById("review-files-input").value = spec.files || "";
      runReviewChange();
    } catch (e) {
      console.error(e);
    }
  });
});

const reviewBtn = document.getElementById("review-btn");
if (reviewBtn) {
  reviewBtn.addEventListener("click", runReviewChange);
}

async function runReviewChange() {
  const change = document.getElementById("review-change-input").value.trim();
  const filesRaw = document.getElementById("review-files-input").value.trim();
  const files = filesRaw
    ? filesRaw.split(",").map((s) => s.trim()).filter(Boolean)
    : [];
  if (!change) return;

  // ensure review view active
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  const nav = document.querySelector('[data-view="review"]');
  if (nav) nav.classList.add("active");
  document.getElementById("view-review").classList.add("active");

  const btn = document.getElementById("review-btn");
  const status = document.getElementById("review-status");
  btn.disabled = true;
  status.textContent = "Comparing change with Hindsight memory…";

  try {
    const res = await fetch(`${API}/api/review-change`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        service: selectedReviewService,
        change_summary: change,
        files,
      }),
    });
    const data = await res.json();
    renderReview(data);
    status.textContent = `Risk: ${data.risk_level} · ${data.warnings?.length || 0} warning(s)`;
  } catch (err) {
    status.textContent = "Error: " + err.message;
  } finally {
    btn.disabled = false;
  }
}

function renderReview(data) {
  const panel = document.getElementById("review-panel");
  panel.classList.remove("hidden");

  const badge = document.getElementById("review-risk-badge");
  badge.textContent = (data.risk_level || "unknown").toUpperCase();
  badge.className = "badge badge-" + (data.risk_level || "unknown");

  document.getElementById("review-summary").textContent = data.summary || "";

  const warns = document.getElementById("review-warnings");
  if (data.warnings && data.warnings.length) {
    warns.innerHTML = data.warnings
      .map(
        (w) => `
      <div class="warn-card sev-${w.severity || "low"}">
        <span class="badge badge-${w.severity || "low"}">${(w.severity || "").toUpperCase()}</span>
        <div class="warn-title">${escapeHtml(w.title || "")}</div>
        <div class="warn-why"><strong>Why:</strong> ${escapeHtml(w.why || "")}</div>
        <div class="warn-rec"><strong>Recommendation:</strong> ${escapeHtml(w.recommendation || "")}</div>
        ${
          w.evidence_ids && w.evidence_ids.length
            ? `<div class="detail" style="margin-top:0.35rem">${w.evidence_ids
                .filter(Boolean)
                .map((id) => `<span class="source-chip">${escapeHtml(String(id))}</span>`)
                .join(" ")}</div>`
            : ""
        }
      </div>`
      )
      .join("");
  } else {
    warns.innerHTML = '<div class="mini-card"><div class="detail">No warnings from Hindsight memory.</div></div>';
  }

  const incEl = document.getElementById("review-incidents");
  incEl.innerHTML = (data.related_incidents || [])
    .map(
      (i) => `
    <div class="mini-card">
      <div class="id">${i.id} ${i.severity ? `<span class="badge badge-${String(i.severity).toLowerCase().replace("-", "")}">${i.severity}</span>` : ""}</div>
      <div class="title">${escapeHtml(i.title || "")}</div>
      ${i.root_cause ? `<div class="detail">Root cause: ${escapeHtml(i.root_cause)}</div>` : ""}
    </div>`
    )
    .join("") || '<div class="mini-card"><div class="detail">None</div></div>';

  document.getElementById("review-rollbacks").innerHTML =
    (data.related_rollbacks || [])
      .map(
        (r) => `
    <div class="mini-card">
      <div class="id">${r.id}</div>
      <div class="title">${escapeHtml(r.title || "")}</div>
      ${r.reason ? `<div class="detail">${escapeHtml(r.reason)}</div>` : ""}
    </div>`
      )
      .join("") || '<div class="mini-card"><div class="detail">None</div></div>';

  document.getElementById("review-reviews").innerHTML =
    (data.related_reviews || [])
      .map((r) => {
        const comments = (r.comments || [])
          .slice(0, 3)
          .map(
            (c) =>
              `<div class="detail">↳ <code>${escapeHtml(String(c.file || ""))}:${c.line ?? ""}</code> — ${escapeHtml((c.body || "").slice(0, 120))}</div>`
          )
          .join("");
        return `
    <div class="mini-card">
      <div class="id">${r.id} · ${r.pr_id || ""} · ${r.state || ""}</div>
      <div class="title">${escapeHtml(r.reviewer || "")}: ${escapeHtml(r.body || "")}</div>
      ${comments}
    </div>`;
      })
      .join("") || '<div class="mini-card"><div class="detail">None</div></div>';

  document.getElementById("review-outcomes").innerHTML =
    (data.related_outcomes || [])
      .map(
        (o) => `
    <div class="mini-card">
      <div class="id">${o.id}</div>
      <div class="title">${escapeHtml(o.title || "")}</div>
      ${o.summary ? `<div class="detail">${escapeHtml(o.summary)}</div>` : ""}
    </div>`
      )
      .join("") || '<div class="mini-card"><div class="detail">None</div></div>';

  document.getElementById("review-sources").innerHTML = (data.sources || [])
    .map(
      (s) =>
        `<span class="source-chip"><span class="type">${s.type || ""}</span>${s.id}</span>`
    )
    .join("");
}
