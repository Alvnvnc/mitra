/* Mitra dashboard — vanilla ES module, no build step.
   The server is the source of truth; this file only renders and posts. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = {
  boot: null,
  view: "today",
  chat: { sessionId: null, messages: [], busy: false, sources: [], trace: [], draft: false },
  memory: { page: "priorities.md", cache: {}, editing: false },
  audit: { tab: "decisions", filter: "all", rows: null, calls: null },
  stats: { days: 7, data: null },
};

/* ------------------------------------------------------------------ utils */

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function tz() {
  return state.boot?.app?.timezone || "Asia/Jakarta";
}

function fmtDate(iso, opts = {}) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz(),
    day: "2-digit",
    month: "short",
    ...opts,
  }).format(d);
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz(),
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  return fmtDate(iso, { hour: "2-digit", minute: "2-digit", hour12: false });
}

function relTime(iso) {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(diff)) return "—";
  if (diff < 45) return "just now";
  if (diff < 3600) return Math.round(diff / 60) + "m ago";
  if (diff < 86400) return Math.round(diff / 3600) + "h ago";
  if (diff < 86400 * 7) return Math.round(diff / 86400) + "d ago";
  return fmtDate(iso);
}

function money(value) {
  const n = Number(value || 0);
  if (n === 0) return "$0.00";
  if (n < 0.01) return "$" + n.toFixed(4);
  return "$" + n.toFixed(2);
}

function pct(value) {
  if (value === null || value === undefined) return "—";
  return Math.round(Number(value) * 100) + "%";
}

function inline(text) {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/_([^_]+)_/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>'
    );
}

function md(src) {
  const text = String(src ?? "");
  if (!text.trim()) return '<p class="muted">Empty page.</p>';
  const lines = text.split("\n").map((line) => line.replace(/\s+$/, ""));
  const out = [];
  const html = (value) => inline(esc(value));
  let para = [];
  let list = null;
  let quote = null;
  let code = null;

  const flushPara = () => {
    if (para.length) {
      out.push("<p>" + html(para.join(" ")) + "</p>");
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      out.push("<" + list.tag + ">" + list.items.map((i) => "<li>" + html(i) + "</li>").join("") + "</" + list.tag + ">");
      list = null;
    }
  };
  const flushQuote = () => {
    if (quote) {
      out.push("<blockquote>" + html(quote.join(" ")) + "</blockquote>");
      quote = null;
    }
  };
  const flushAll = () => { flushPara(); flushList(); flushQuote(); };

  for (const line of lines) {
    if (line.startsWith("```")) {
      flushAll();
      if (code === null) code = [];
      else { out.push("<pre><code>" + esc(code.join("\n")) + "</code></pre>"); code = null; }
      continue;
    }
    if (code !== null) { code.push(line); continue; }
    if (!line.trim()) { flushAll(); continue; }
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) { flushAll(); out.push("<h" + h[1].length + ">" + html(h[2]) + "</h" + h[1].length + ">"); continue; }
    if (/^---+$/.test(line.trim())) { flushAll(); out.push("<hr>"); continue; }
    if (/^>\s?/.test(line)) {
      flushPara(); flushList();
      quote = quote || [];
      quote.push(line.replace(/^>\s?/, ""));
      continue;
    }
    const ul = line.match(/^[-*]\s+(.*)$/);
    const ol = line.match(/^\d+\.\s+(.*)$/);
    if (ul || ol) {
      flushPara(); flushQuote();
      const tag = ul ? "ul" : "ol";
      if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
      list.items.push(ul ? ul[1] : ol[1]);
      continue;
    }
    para.push(line.trim());
  }
  flushPara(); flushList(); flushQuote();
  if (code !== null) out.push("<pre><code>" + esc(code.join("\n")) + "</code></pre>");
  return out.join("\n");
}

function providerLabel(provider) {
  if (!provider) return "model";
  if (provider === "seed") return "seeded";
  if (provider === "demo") return "local demo model";
  if (provider === "nebius") return "nemotron";
  return provider;
}

function chip(runState) {
  const map = {
    done: ["chip-done", "Verified"],
    failed: ["chip-failed", "Failed"],
    delivery_failed: ["chip-delivery", "Delivery failed"],
    running: ["chip-pending", "Running"],
    queued: ["chip-pending", "Queued"],
    blocked: ["chip-paused", "Blocked"],
    paused: ["chip-paused", "Paused"],
    retired: ["chip-paused", "Retired"],
    active: ["chip-done", "Active"],
  };
  const [cls, label] = map[runState] || ["chip-neutral", runState || "Unknown"];
  return '<span class="chip ' + cls + '"><span class="dot"></span>' + esc(label) + "</span>";
}

function decisionChip(decision) {
  const map = {
    allowed: ["chip-done", "allowed"],
    executed: ["chip-done", "executed"],
    approved: ["chip-done", "approved"],
    denied: ["chip-failed", "denied"],
    approval_required: ["chip-delivery", "approval"],
    error: ["chip-failed", "error"],
    rejected: ["chip-paused", "rejected"],
  };
  const [cls, label] = map[decision] || ["chip-neutral", decision];
  return '<span class="chip ' + cls + '"><span class="dot"></span>' + esc(label) + "</span>";
}

function riskTag(risk) {
  return '<span class="risk ' + esc(risk || "low") + '">' + esc(risk || "low") + "</span>";
}

function providerTag() {
  if (!state.boot) return "";
  const live = state.boot.router.provider === "nebius";
  return (
    '<span class="provider-tag ' + (live ? "live" : "") + '">' +
    (live ? "Nemotron · Nebius Token Factory" : "Local demo model · no API key") +
    "</span>"
  );
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.error || detail;
    } catch (_) { /* noop */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function toast(message, kind = "ok") {
  const node = document.createElement("div");
  node.className = "toast" + (kind === "error" ? " error" : "");
  node.innerHTML =
    '<svg class="ico"><use href="#i-' + (kind === "error" ? "alert" : "check") + '"/></svg><span>' +
    esc(message) + "</span>";
  $("#toasts").appendChild(node);
  setTimeout(() => node.remove(), kind === "error" ? 6500 : 3800);
}

async function withBusy(button, fn) {
  if (!button) return fn();
  const original = button.innerHTML;
  button.disabled = true;
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.innerHTML = original;
  }
}

/* ------------------------------------------------------------------ shell */

function greeting() {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: tz() }).format(new Date())
  );
  if (hour < 5) return "Still up";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  if (hour < 21) return "Good evening";
  return "Late shift";
}

function ownerName() {
  const owner = state.boot?.app?.owner || "";
  return owner.split(" ")[0] || "there";
}

function needsCount() {
  if (!state.boot) return 0;
  return (state.boot.proposals?.length || 0) + (state.boot.approvals?.length || 0);
}

function updateShell() {
  if (!state.boot) return;
  $$("[data-count]").forEach((el) => {
    const kind = el.dataset.count;
    let value = 0;
    if (kind === "needs") value = needsCount();
    if (kind === "proposals") value = needsCount();
    if (kind === "commitments") value = state.boot.commitments.filter((c) => c.state === "active").length;
    el.textContent = value;
    el.hidden = value === 0;
  });
  $("#version").textContent = "v" + state.boot.app.version;
  const live = state.boot.router.provider === "nebius";
  $("#providerName").textContent = live ? "Nemotron · Nebius" : "Local demo model";
  $("#providerNote").textContent = live
    ? "Super for chat · Nano for extraction · Ultra for planning"
    : state.boot.router.degraded_reason || "Set NEBIUS_API_KEY for live inference";
  $("#providerDot").className = "dot " + (live ? "" : "amber");
  $("#providerState").textContent = live ? "live inference" : "demo fallback";
  $("#demoBanner").hidden = !state.boot.app.demo_mode;
  $("#resetDemo").hidden = !(state.boot.app.demo_mode && state.boot.app.is_admin);
  syncBannerHeight();
}

function syncBannerHeight() {
  const banner = $("#demoBanner");
  const height = banner && !banner.hidden ? banner.offsetHeight : 0;
  document.documentElement.style.setProperty("--banner-h", height + "px");
}

window.addEventListener("resize", syncBannerHeight);

function updateClock() {
  if (!state.boot) return;
  const now = new Date();
  const text = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz(), hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(now);
  $("#clock").textContent = text + " " + (state.boot.app.timezone.split("/")[1] || "");
}

function setView(name, crumb) {
  state.view = name;
  $("#view").classList.toggle("chat-view", name === "chat");
  $$("[data-nav]").forEach((el) => el.classList.toggle("active", el.dataset.nav === name));
  $("#crumbs").innerHTML = crumb || '<span class="crumb-current">' + esc(name) + "</span>";
}

function route() {
  if (!state.boot) return;
  const hash = location.hash.replace(/^#\/?/, "") || "today";
  const [section, id] = hash.split("/");
  closeDrawer();
  const main = $("#main");
  if (main) main.scrollTop = 0;
  if (section === "chat") { setView("chat", '<span class="crumb-current">Chat</span>'); renderChat(); return; }
  if (section === "commitments" && id) {
    setView("commitments", '<span>Commitments</span><span class="sep">/</span><span class="crumb-current">Detail</span>');
    renderCommitmentDetail(id);
    return;
  }
  if (section === "commitments") { setView("commitments", '<span class="crumb-current">Commitments</span>'); renderCommitments(); return; }
  if (section === "memory") { setView("memory", '<span class="crumb-current">Memory</span>'); renderMemory(); return; }
  if (section === "skills") { setView("skills", '<span class="crumb-current">Skills &amp; tools</span>'); renderSkills(); return; }
  if (section === "audit") { setView("audit", '<span class="crumb-current">Audit</span>'); renderAudit(); return; }
  if (section === "stats") { setView("stats", '<span class="crumb-current">Stats</span>'); renderStats(); return; }
  setView("today", '<span class="crumb-current">Today</span>');
  renderToday();
}

async function boot() {
  try {
    state.boot = await api("/api/bootstrap");
  } catch (err) {
    $("#view").innerHTML =
      '<div class="panel panel-pad"><h1 class="display">The dashboard is not responding.</h1>' +
      '<p class="page-sub">' + esc(err.message) + "</p></div>";
    return;
  }
  updateShell();
  updateClock();
  route();
  setInterval(updateClock, 30000);
  setInterval(silentRefresh, 60000);
}

async function silentRefresh() {
  if (document.hidden) return;
  if (!$("#drawer").hidden || !$("#dialog").hidden || !$("#palette").hidden) return;
  if (state.chat.busy) return;
  const active = document.activeElement;
  if (active && ["INPUT", "TEXTAREA"].includes(active.tagName)) return;
  try {
    state.boot = await api("/api/bootstrap");
    updateShell();
    if (["today", "commitments"].includes(state.view) && !(location.hash.includes("/") && location.hash.split("/").length > 2)) {
      route();
    }
  } catch (_) { /* keep the current view */ }
}

/* ------------------------------------------------------------------ today */

function needsItems() {
  const items = [];
  for (const proposal of state.boot.proposals || []) {
    items.push({
      kind: "memory",
      id: proposal.id,
      title: proposal.title,
      body: "Proposed for " + proposal.page + " — " + (proposal.rationale || "consolidated from recent sessions"),
      actions:
        '<button class="btn btn-sm btn-green" data-act="approve-proposal" data-id="' + proposal.id + '">Approve</button>' +
        '<button class="btn btn-sm" data-act="reject-proposal" data-id="' + proposal.id + '">Reject</button>',
    });
  }
  for (const approval of state.boot.approvals || []) {
    const preview = approval.args?.text || approval.args?.title || JSON.stringify(approval.args || {});
    items.push({
      kind: "tool",
      id: approval.id,
      title: approval.tool + " needs approval",
      body: String(preview).slice(0, 150),
      actions:
        '<button class="btn btn-sm btn-green" data-act="approve-tool" data-id="' + approval.id + '">Approve once</button>' +
        '<button class="btn btn-sm" data-act="deny-tool" data-id="' + approval.id + '">Deny</button>',
    });
  }
  return items;
}

function renderToday() {
  const b = state.boot;
  const items = needsItems();
  const stats = b.stats;
  const active = b.commitments.filter((c) => c.state === "active");
  const failed = b.commitments.filter((c) => c.latest_run && ["failed", "delivery_failed"].includes(c.latest_run.state));
  const verified = b.commitments.filter((c) => c.latest_run?.state === "done").length;

  const kpis =
    '<div class="stat-strip">' +
    kpi("Runs · 7 days", String(stats.total), "runs", "evidence gate on every one", "accent-green") +
    kpi("Verified", pct(stats.success_rate), "", (stats.failed || 0) + " failed · " + (stats.delivery_failed || 0) + " delivery", stats.success_rate >= 0.8 ? "accent-green" : "accent-amber") +
    kpi("Needs you", String(needsCount()), "", items.length ? "memory + tool decisions" : "inbox is clear", items.length ? "accent-amber" : "accent-green") +
    kpi("Inference · 7d", money(b.usage.cost_usd), "", b.usage.calls + " calls · " + (b.usage.avg_latency_s || 0).toFixed(1) + "s avg", "accent-amber") +
    "</div>";

  const alert = (b.notices || []).length
    ? '<div class="alert-strip"><svg class="ico"><use href="#i-alert"/></svg><div><strong>Delivery failure is visible without asking.</strong> ' +
      esc((b.notices[0].commitment || "A commitment").replace(/`/g, "").replace(/\s*\(\s*\)/g, "").trim()) + " · " +
      esc(b.notices[0].stage || "delivery") + " stage · " + esc(b.notices[0].error || "see notice") +
      '</div><button class="btn btn-sm" data-act="notice" data-id="' + esc(b.notices[0].name) + '">View notice</button></div>'
    : "";

  const heroNote =
    '<div class="hero-note"><strong>What the ledger says</strong>' +
    active.length + " active commitment" + (active.length === 1 ? "" : "s") + ". " +
    verified + " of " + b.commitments.length + " have a verified last result" +
    (failed.length ? ". " + failed.length + " need a look before you trust the next run." : ". Nothing is silently broken.") +
    "</div>";

  const needHtml = items.length
    ? '<div class="need-list">' + items.map((item) =>
        '<div class="need-item"><div class="need-glyph"><svg class="ico"><use href="#i-' +
        (item.kind === "memory" ? "memory" : "lock") + '"/></svg></div><div><div class="need-title">' +
        esc(item.title) + '</div><div class="need-body">' + esc(item.body) + '</div></div><div class="need-actions">' +
        item.actions + "</div></div>").join("") + "</div>"
    : '<div class="need-empty"><strong>Inbox clear.</strong>Nothing is waiting on a human decision.</div>';

  const rows = b.commitments.map((c) => {
    const run = c.latest_run;
    return (
      '<a class="commit-row" href="#/commitments/' + esc(c.id) + '">' +
      '<div><div class="commit-title">' + esc(c.title) + (c.state !== "active" ? ' <span class="chip chip-paused"><span class="dot"></span>' + esc(c.state) + "</span>" : "") + "</div>" +
      '<div class="commit-sub"><span class="mono">' + esc(c.skill) + "</span><span>·</span><span>" + esc(c.delivery_channel) + "</span>" +
      (c.upcoming_version ? '<span>·</span><span style="color:var(--amber)">change scheduled</span>' : "") + "</div></div>" +
      '<div class="commit-cell col-schedule"><span class="mono">' + esc(c.schedule) + '</span><div class="tiny muted">' + esc(c.timezone) + "</div></div>" +
      '<div class="commit-cell col-version"><span class="mono">v' + (c.active_version?.id || "—") + "</span><div class=\"tiny muted\">" + (c.version_count || 0) + " version(s)</div></div>" +
      '<div class="commit-cell">' + (run ? chip(run.state) + '<div class="tiny muted" style="margin-top:3px">' + relTime(run.at) + "</div>" : '<span class="muted tiny">no runs</span>') + "</div>" +
      '<div class="row-chevron"><svg class="ico"><use href="#i-chevron"/></svg></div></a>'
    );
  }).join("");

  const activity = (b.events || []).filter((e) => e.kind !== "demo_seeded").slice(0, 8).map((event) => {
    const color = /fail|error|denied/.test(event.kind) ? "red" : /deliver|run/.test(event.kind) ? "green" : /proposal|instruction/.test(event.kind) ? "blue" : "";
    return '<li><span class="act-dot ' + color + '"></span><div><div class="act-main"><b>' +
      esc(event.kind.replaceAll("_", " ")) + "</b> " + esc(summarizeEvent(event)) + "</div>" +
      '<div class="act-time">' + fmtDateTime(event.at) + " · " + relTime(event.at) + "</div></div></li>";
  }).join("");

  $("#view").innerHTML =
    '<div class="hero"><div><div class="kicker">' +
    esc(new Intl.DateTimeFormat("en-GB", { timeZone: tz(), weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date())) +
    " · " + esc(tz().replace("_", " ")) + '</div><h1 class="display">' + greeting() + ", " + esc(ownerName()) + ".<br><em>" +
    (needsCount() ? needsCount() + " thing" + (needsCount() === 1 ? "" : "s") + " need you." : "The ledger is quiet.") +
    "</em></h1><p class=\"page-sub\">Delegated work, verified. Every run carries evidence, every delivery is a separate state, and nothing is written to memory without your approval.</p></div>" +
    heroNote + "</div>" +
    alert +
    kpis +
    '<div class="split" style="margin-top:20px"><div class="stack">' +
    '<section class="panel"><div class="panel-head"><h3>Needs you</h3><span class="hint">' + items.length + " open</span></div>" + needHtml + "</section>" +
    '<section class="panel"><div class="panel-head"><h3>Commitments</h3><a class="hint" href="#/commitments">All commitments →</a></div>' +
    '<div class="commit-head" aria-hidden="true"><span>Commitment</span><span class="col-schedule">Schedule</span><span class="col-version">Version</span><span>Last run</span><span></span></div>' +
    '<div class="commit-list">' + rows + "</div></section>" +
    "</div>" +
    '<div class="stack">' +
    '<section class="panel"><div class="panel-head"><h3>Latest verified brief</h3><span class="hint" id="briefHint">loading…</span></div><div class="brief" id="briefBody"><div class="skeleton" style="height:96px"></div></div></section>' +
    '<section class="panel"><div class="panel-head"><h3>Activity</h3><span class="hint">ledger events</span></div><ul class="activity">' + (activity || '<li><span class="act-dot"></span><div class="act-main muted">No events yet.</div></li>') + "</ul></section>" +
    "</div></div>";

  loadBrief();
}

function kpi(label, value, suffix, meta, accent) {
  return (
    '<div class="kpi ' + accent + '"><div class="kpi-label">' + esc(label) + '</div><div class="kpi-value">' +
    esc(value) + (suffix ? "<small>" + esc(suffix) + "</small>" : "") + "</div>" +
    '<div class="kpi-meta">' + esc(meta) + "</div></div>"
  );
}

function summarizeEvent(event) {
  const detail = event.detail && typeof event.detail === "object" ? event.detail : {};
  if (event.kind === "run_failed") return detail.error ? String(detail.error).slice(0, 90) : "";
  if (event.kind === "delivery_failed") return detail.error ? String(detail.error).slice(0, 90) : "";
  if (event.kind === "completion_claimed") return "evidence gate passed";
  if (event.kind === "proposal_created") return "for " + (detail.page ?? "memory");
  if (event.kind === "proposal_decided") {
    return "#" + (detail.proposal_id ?? "") + " " + (detail.decision ?? "") + (detail.page ? " · " + detail.page : "");
  }
  if (event.kind === "memory_applied") return "memory updated: " + (detail.page ?? "");
  if (event.kind === "memory_user_edit") return "you edited " + (detail.page ?? "");
  if (event.kind === "chat_reply") return "reply via " + providerLabel(detail.provider);
  if (event.kind === "web_search") return "“" + (detail.query || "").slice(0, 60) + "”";
  if (event.kind === "consolidation_run") return (detail.created?.length ?? detail.created ?? 0) + " proposal(s) from a " + (detail.window ?? "24h") + " window";
  if (event.kind === "instruction_added") return "v" + (detail.version_id ?? "") + " in force from " + fmtDate(detail.effective_from);
  if (event.kind === "run_created") return "instruction v" + (detail.instruction_version_id ?? "");
  if (event.kind === "commitment_created") return "“" + (detail.title ?? "") + "”";
  if (event.kind === "commitment_state") return "→ " + (detail.state || "");
  if (event.kind === "note_written") return "note " + (detail.note_id ?? "");
  if (event.kind === "tool_call") return (detail.tool || "") + " · " + (detail.decision || "");
  if (event.kind === "tool_exec") return (detail.tool || "tool") + " ran";
  if (event.kind === "scheduler_error") return String(detail).slice(0, 90);
  if (event.kind === "manual_run") return "triggered by you";
  if (event.kind === "consolidation") return "window " + (detail.window ?? "24h");
  return typeof event.detail === "string" ? event.detail.slice(0, 90) : "";
}

async function loadBrief() {
  const done = state.boot.commitments
    .map((c) => c.latest_run)
    .filter((r) => r && r.state === "done" && (r.evidence || []).some((e) => e.kind === "artifact"))
    .sort((a, b) => new Date(b.at) - new Date(a.at))[0];
  const holder = $("#briefBody");
  if (!holder) return;
  if (!done) {
    holder.innerHTML = '<p class="muted small">No verified artifact yet. Run a commitment to produce one.</p>';
    $("#briefHint").textContent = "none";
    return;
  }
  try {
    const data = await api("/api/runs/" + done.id);
    const text = data.artifact || "";
    holder.innerHTML = '<div class="md">' + md(text.slice(0, 1600)) + "</div>" +
      '<div class="brief-meta"><span class="tag">' + esc(data.commitment.title) + '</span><span class="tag">run ' + esc(done.id) + '</span>' +
      '<span class="tag">instruction v' + esc(done.instruction_version_id) + '</span><span class="tag">' + fmtDateTime(done.at) + "</span></div>";
    $("#briefHint").textContent = relTime(done.at);
  } catch (err) {
    holder.innerHTML = '<p class="error-text">' + esc(err.message) + "</p>";
  }
}

/* ------------------------------------------------------------------ chat */

async function renderChat() {
  const sessions = state.boot.sessions || [];
  if (!state.chat.sessionId && !state.chat.draft) {
    state.chat.sessionId = sessions[0]?.id || null;
    state.chat.messages = [];
  }
  const active = sessions.find((s) => s.id === state.chat.sessionId);

  $("#view").innerHTML =
    '<div class="chat-layout">' +
    '<aside class="chat-side"><div class="chat-side-head"><h2>Conversations</h2><button class="icon-btn" data-act="new-chat" aria-label="New conversation"><svg class="ico"><use href="#i-plus"/></svg></button></div><div class="session-list" id="sessionList">' +
    (sessions.length ? sessions.map((s) =>
      '<button class="session-item ' + (s.id === state.chat.sessionId ? "active" : "") + '" data-act="session" data-id="' + esc(s.id) + '">' +
      esc(s.title) + '<span class="s-meta">' + relTime(s.updated_at) + " · " + s.messages + " msg</span></button>").join("")
      : '<p class="ctx-note" style="padding:8px">No conversations yet.</p>') +
    "</div></aside>" +
    '<section class="chat-main"><header class="chat-head"><button class="icon-btn chat-list-btn" data-act="chat-sessions" aria-label="Conversations"><svg class="ico"><use href="#i-chat"/></svg></button><div><h1>' + esc(active?.title || "New conversation") + '</h1><div class="mono">' +
    esc(state.chat.sessionId || "draft") + "</div></div><div class=\"spacer\"></div>" + providerTag() + "</header>" +
    '<div class="chat-scroll" id="chatScroll"><div class="chat-inner" id="chatInner">' + chatBody() + "</div></div>" +
    '<div class="composer"><div class="composer-inner"><div class="composer-box"><textarea id="chatInput" rows="1" placeholder="Ask about a commitment, a memory, or search the web…" aria-label="Message"></textarea><button class="send-btn" id="sendBtn" aria-label="Send"><svg class="ico"><use href="#i-send"/></svg></button></div>' +
    '<div class="composer-hint"><span>Enter to send · Shift+Enter for a new line</span><span>Tools are allowlisted and audited</span></div></div></div></section>' +
    '<aside class="chat-context"><div class="ctx-block"><div class="ctx-label">Model</div><p class="ctx-note">' +
    (state.boot.router.provider === "nebius"
      ? "Nemotron 3 Super 120B via Nebius Token Factory. Thinking off for chat; tool calls are policy-checked."
      : "Local deterministic composer. The live path is Nemotron on Nebius; this fallback keeps the demo honest when no key is present.") +
    "</p></div><div class=\"ctx-block\"><div class=\"ctx-label\">Retrieved this turn</div><ul class=\"ctx-list\" id=\"ctxSources\"><li>nothing yet</li></ul></div>" +
    '<div class="ctx-block"><div class="ctx-label">Trace</div><div id="ctxTrace" class="ctx-note">The trace appears after the first reply.</div></div>' +
    '<div class="ctx-block"><div class="ctx-label">Write discipline</div><p class="ctx-note">Chat is read-only for memory. Proposed writes wait in the approval inbox.</p></div></aside></div>';

  if (state.chat.sessionId && state.chat.messages.length === 0) {
    try {
      const data = await api("/api/sessions/" + state.chat.sessionId + "/messages");
      state.chat.messages = data.messages || [];
      $("#chatInner").innerHTML = chatBody();
      bindComposer();
      scrollChat();
      const lastReply = [...state.chat.messages].reverse().find((m) => m.role === "assistant" && m.meta);
      if (lastReply) {
        const meta = lastReply.meta || {};
        updateContextPanel(meta.sources || [], meta.trace || []);
      }
    } catch (err) {
      toast(err.message, "error");
    }
  } else {
    bindComposer();
    scrollChat();
  }
  if (state.chat.sources.length) updateContextPanel(state.chat.sources, state.chat.trace);
}

function chatBody() {
  if (!state.chat.messages.length) {
    const suggestions = [
      ["What needs a decision today?", "Read the ledger, not a summary of it."],
      ["What do you remember about Ellis?", "Show the memory pages and their sources."],
      ["Search for red-edge indices in oil palm", "A governed web_search call, with the lane named."],
      ["Did yesterday's brief actually deliver?", "Separate result state from delivery state."],
    ];
    return (
      '<div class="empty-chat"><div class="kicker" style="justify-content:center">Persistent session · bounded context</div>' +
      '<h1 class="display">What should we <em>get done?</em></h1>' +
      "<p>Ask about commitments or memory. I will show what I retrieved, which tools ran, and what still needs your approval.</p>" +
      '<div class="suggest">' + suggestions.map(([title, sub]) =>
        '<button data-act="suggest" data-text="' + esc(title) + '"><b>' + esc(title) + "</b>" + esc(sub) + "</button>").join("") + "</div></div>"
    );
  }
  return state.chat.messages.map(messageMarkup).join("");
}

function messageMarkup(message) {
  if (message.role === "user") {
    return '<div class="msg msg-user"><div class="bubble">' + esc(message.content) + "</div></div>";
  }
  const meta = message.meta || {};
  const sources = meta.sources || [];
  const trace = meta.trace || [];
  const isError = meta.error;
  return (
    '<div class="msg msg-agent ' + (isError ? "msg-error" : "") + '"><div class="avatar">M</div><div>' +
    '<div class="agent-name"><b>Mitra</b>' + (meta.provider ? '<span>' + esc(providerLabel(meta.provider)) + "</span>" : "") +
    (meta.cost_usd !== undefined ? '<span>· ' + money(meta.cost_usd) + "</span>" : "") +
    '<span>· ' + (message.at ? fmtTime(message.at) : "now") + "</span></div>" +
    '<div class="agent-body md">' + md(message.content) + "</div>" +
    (sources.length ? '<div class="source-chips">' + sources.slice(0, 6).map((s) => '<span class="tag">' + esc(s) + "</span>").join("") + "</div>" : "") +
    (trace.length ? '<details class="trace"><summary><svg class="ico"><use href="#i-chevron"/></svg><span>Trace · ' + trace.length + " steps</span></summary><div class=\"trace-list\">" +
      trace.map((t) => '<div class="trace-row"><span class="t-stage">' + esc(t.stage) + "</span><span>" + esc(t.label) + "</span></div>").join("") +
      "</div></details>" : "") +
    "</div></div>"
  );
}

function bindComposer() {
  const input = $("#chatInput");
  const send = $("#sendBtn");
  if (!input || !send) return;
  const resize = () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  };
  input.addEventListener("input", resize);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  });
  send.addEventListener("click", () => sendChat());
  if (window.innerWidth > 980) input.focus();
}

function scrollChat() {
  const el = $("#chatScroll");
  if (el) el.scrollTop = el.scrollHeight;
}

async function sendChat(textOverride) {
  const input = $("#chatInput");
  const text = (textOverride ?? input?.value ?? "").trim();
  if (!text || state.chat.busy) return;
  state.chat.busy = true;
  const send = $("#sendBtn");
  if (send) send.disabled = true;
  if (input) { input.value = ""; input.style.height = "auto"; }

  if (!state.chat.sessionId) {
    try {
      const created = await api("/api/sessions", { method: "POST", body: JSON.stringify({ title: text.slice(0, 60) }) });
      state.chat.draft = false;
      state.chat.sessionId = created.session_id;
    } catch (err) {
      toast(err.message, "error");
      state.chat.busy = false;
      if (send) send.disabled = false;
      return;
    }
  }

  state.chat.messages.push({ role: "user", content: text, at: new Date().toISOString() });
  state.chat.messages.push({ role: "assistant", content: "", pending: true, at: new Date().toISOString() });
  $("#chatInner").innerHTML = chatBody();
  scrollChat();
  const pending = $$("#chatInner .msg-agent").at(-1);
  pending.querySelector(".agent-body").innerHTML =
    '<div class="stage-row" id="stageRow"><span class="stage running"><span class="dot"></span>retrieving memory</span></div>';
  if ($("#ctxSources")) $("#ctxSources").innerHTML = "<li>retrieving…</li>";

  const stages = [];

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.chat.sessionId, message: text }),
    });
    if (!res.ok || !res.body) {
      let detail = "HTTP " + res.status;
      try {
        const body = await res.json();
        detail = body.detail || body.error || detail;
        if (body.retry_after_s) detail += " (retry in " + Math.max(1, Math.round(body.retry_after_s)) + "s)";
      } catch (_) {}
      throw new Error(detail);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalText = null;
    let doneMeta = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === "context") {
          state.chat.sources = event.sources || [];
          stages.push({ label: "context · " + (event.sources?.length || 0) + " sources", cls: "ok" });
          updateStages(pending, stages);
          updateContextPanel(state.chat.sources, state.chat.trace);
        } else if (event.type === "stage") {
          stages.push({ label: "model · round " + event.round, cls: "" });
          updateStages(pending, stages);
        } else if (event.type === "tool") {
          stages.push({ label: event.tool + " · " + event.status, cls: event.status === "denied" ? "denied" : event.status === "ok" ? "ok" : "" });
          updateStages(pending, stages);
        } else if (event.type === "final") {
          finalText = event.text;
          pending.querySelector(".agent-body").innerHTML = md(finalText);
        } else if (event.type === "done") {
          doneMeta = event;
        } else if (event.type === "error") {
          throw new Error(event.error);
        }
      }
    }

    if (finalText === null) finalText = "The stream closed before a final answer.";
    const last = state.chat.messages[state.chat.messages.length - 1];
    last.pending = false;
    last.content = finalText;
    last.meta = {
      provider: doneMeta?.provider,
      model: doneMeta?.model,
      cost_usd: doneMeta?.cost_usd,
      sources: doneMeta?.sources || state.chat.sources,
      trace: doneMeta?.trace || [],
    };
    state.chat.trace = last.meta.trace;
    $("#chatInner").innerHTML = chatBody();
    updateContextPanel(last.meta.sources, last.meta.trace);
    scrollChat();
    refreshSessions();
  } catch (err) {
    const last = state.chat.messages[state.chat.messages.length - 1];
    last.pending = false;
    last.content = "I could not complete that request.\n\n`" + err.message + "`";
    last.meta = { error: true };
    $("#chatInner").innerHTML = chatBody();
    toast(err.message, "error");
  } finally {
    state.chat.busy = false;
    if (send) send.disabled = false;
    if (input) input.focus();
    refreshBootBadges();
  }
}

function updateStages(pending, stages) {
  const row = pending?.querySelector("#stageRow");
  if (!row) return;
  row.innerHTML = stages.map((s) => '<span class="stage ' + s.cls + '"><span class="dot"></span>' + esc(s.label) + "</span>").join("");
}

function updateContextPanel(sources, trace) {
  const list = $("#ctxSources");
  if (list) list.innerHTML = (sources && sources.length)
    ? sources.map((s) => "<li>" + esc(s) + "</li>").join("")
    : "<li>no memory matched</li>";
  const traceEl = $("#ctxTrace");
  if (traceEl && trace) {
    traceEl.innerHTML = trace.length
      ? trace.map((t) => '<div class="trace-row"><span class="t-stage">' + esc(t.stage) + "</span><span>" + esc(t.label) + "</span></div>").join("")
      : "No trace yet.";
  }
}

async function refreshSessions() {
  try {
    const data = await api("/api/bootstrap");
    state.boot = data;
    updateShell();
    const list = $("#sessionList");
    if (list) {
      list.innerHTML = (data.sessions || []).map((s) =>
        '<button class="session-item ' + (s.id === state.chat.sessionId ? "active" : "") + '" data-act="session" data-id="' + esc(s.id) + '">' +
        esc(s.title) + '<span class="s-meta">' + relTime(s.updated_at) + " · " + s.messages + " msg</span></button>").join("");
    }
  } catch (_) { /* non-fatal */ }
}

async function refreshBootBadges() {
  try {
    state.boot = await api("/api/bootstrap");
    updateShell();
  } catch (_) {}
}

async function openSession(id) {
  if (state.chat.busy) return;
  state.chat.draft = false;
  state.chat.sessionId = id;
  state.chat.messages = [];
  state.chat.sources = [];
  state.chat.trace = [];
  await renderChat();
}

/* ---------------------------------------------------------------- commitments */

function renderCommitments() {
  const list = state.boot.commitments;
  const rows = list.map((c) => {
    const run = c.latest_run;
    return '<tr class="clickable" data-act="open-commitment" data-id="' + esc(c.id) + '">' +
      '<td data-label="Commitment"><div class="cell-strong">' + esc(c.title) + "</div><div class=\"cell-sub mono\">" + esc(c.id) + "</div></td>" +
      '<td data-label="Schedule"><span class="mono">' + esc(c.schedule) + '</span><div class="cell-sub">' + esc(c.timezone) + "</div></td>" +
      '<td data-label="Skill / lane" class="col-skill"><span class="mono">' + esc(c.skill) + '</span><div class="cell-sub">' + esc(c.delivery_channel) + "</div></td>" +
      '<td data-label="Instruction" class="col-instruction"><span class="mono">v' + esc(c.active_version?.id ?? "—") + "</span>" + (c.upcoming_version ? '<div class="cell-sub" style="color:var(--amber)">change scheduled</div>' : "") + "</td>" +
      '<td data-label="State">' + chip(c.state) + "</td>" +
      '<td data-label="Last run">' + (run ? chip(run.state) + '<div class="cell-sub">' + relTime(run.at) + "</div>" : '<span class="muted">none</span>') + "</td>" +
      '<td data-label="Runs · 7d" class="right mono col-runs">' + c.run_count_7d + "</td></tr>";
  }).join("");

  $("#view").innerHTML =
    '<div class="page-head"><div><div class="kicker">Delegated work</div><h1 class="display">Commitments</h1>' +
    '<p class="page-sub">A commitment is the central unit: a recurring piece of work with versioned instructions, evidence-gated runs and a delivery state that is never assumed.</p></div></div>' +
    '<div class="alert-strip alert-info"><svg class="ico"><use href="#i-lock"/></svg>' +
    '<div><strong>Instruction truth is enforced in code.</strong> The scheduler resolves the latest approved version effective at run time; a change dated “tomorrow” cannot leak into today’s run.</div></div>' +
    '<section class="panel"><div class="panel-head"><h3>All commitments</h3><span class="hint">' + list.length + " total</span></div><div class=\"table-wrap\"><table class=\"data stackable\"><thead><tr><th>Commitment</th><th>Schedule</th><th>Skill / lane</th><th>Instruction</th><th>State</th><th>Last run</th><th class=\"right\">Runs · 7d</th></tr></thead><tbody>" +
    (rows || '<tr><td colspan="7" class="muted">No commitments yet.</td></tr>') + "</tbody></table></div></section>";
}

async function renderCommitmentDetail(id) {
  $("#view").innerHTML = '<div class="panel panel-pad"><div class="skeleton" style="height:180px"></div></div>';
  let data;
  try {
    data = await api("/api/commitments/" + id);
  } catch (err) {
    $("#view").innerHTML = '<div class="panel panel-pad"><h1 class="display">Not found</h1><p class="page-sub">' + esc(err.message) + '</p><a class="btn" href="#/commitments">Back</a></div>';
    return;
  }
  const c = data;
  $("#crumbs").innerHTML =
    '<span>Commitments</span><span class="sep">/</span><span class="crumb-current">' + esc(c.title) + "</span>";
  const runs = c.runs || [];
  const versions = c.versions || [];
  const active = c.active_version;
  const upcoming = c.upcoming_version;

  const runsTable = runs.map((run) =>
    '<tr class="clickable" data-act="open-run" data-id="' + esc(run.id) + '">' +
    "<td>" + chip(run.state) + "</td>" +
    '<td class="mono nowrap">' + fmtDateTime(run.at) + "</td>" +
    '<td class="mono">v' + run.instruction_version_id + "</td>" +
    "<td>" + (run.evidence?.length
      ? '<span class="tag">' + run.evidence.filter((e) => e.check_result === "passed").length + "/" + run.evidence.length + " passed</span>"
      : '<span class="muted">none</span>') + "</td>" +
    "<td>" + (run.delivered_at ? '<span class="chip chip-done"><span class="dot"></span>delivered ' + fmtTime(run.delivered_at) + "</span>" : run.state === "delivery_failed" ? '<span class="chip chip-delivery"><span class="dot"></span>failed</span>' : '<span class="muted tiny">—</span>') + "</td>" +
    '<td class="cell-sub">' + (run.error ? esc(run.error).slice(0, 70) : "") + "</td></tr>").join("");

  const versionsTable = versions.map((v) =>
    '<tr><td class="mono">v' + v.id + "</td><td>" + esc(v.content) + "</td>" +
    '<td class="mono nowrap">' + fmtDateTime(v.effective_from) + "</td>" +
    "<td>" + (v.is_future ? '<span class="chip chip-pending"><span class="dot"></span>scheduled</span>' : v.state === "approved" ? '<span class="chip chip-done"><span class="dot"></span>approved</span>' : chip(v.state)) + "</td>" +
    '<td class="mono">' + (v.supersedes_id ? "v" + v.supersedes_id : "—") + "</td></tr>").join("");

  $("#view").innerHTML =
    '<div class="page-head"><div><div class="kicker"><a href="#/commitments">Commitments</a> / ' + esc(c.skill) + '</div><h1 class="display">' + esc(c.title) + '</h1>' +
    '<div class="row-wrap" style="margin-top:10px">' + chip(c.state) + '<span class="tag mono">' + esc(c.schedule) + " " + esc(c.timezone) + '</span><span class="tag mono">' + esc(c.delivery_channel) + '</span><span class="tag mono">v' + (active?.id || "—") + "</span></div></div>" +
    '<div class="row"><button class="btn" data-act="new-instruction" data-id="' + esc(c.id) + '">New instruction version</button>' +
    '<button class="btn btn-green" data-act="run-now" data-id="' + esc(c.id) + '"><svg class="ico"><use href="#i-play"/></svg>Run now</button>' +
    '<button class="btn" data-act="toggle-state" data-id="' + esc(c.id) + '" data-state="' + (c.state === "active" ? "paused" : "active") + '">' + (c.state === "active" ? "Pause" : "Resume") + "</button></div></div>" +

    '<div class="split"><div class="stack">' +
    '<section class="panel"><div class="panel-head"><h3>Instruction in force</h3><span class="hint">v' + (active?.id || "—") + " · effective " + (active ? fmtDateTime(active.effective_from) : "—") + "</span></div><div class=\"panel-body\">" +
    (active ? '<div class="md">' + md(active.content) + "</div>" +
      '<div class="row-wrap" style="margin-top:12px"><span class="tag mono">approved by ' + esc(active.approved_by) + "</span>" +
      Object.entries(active.params || {}).map(([k, v]) => '<span class="tag mono">' + esc(k) + "=" + esc(v) + "</span>").join("") + "</div>"
      : '<p class="error-text">No approved instruction is effective right now. Runs would be blocked, not guessed.</p>') +
    "</div></section>" +
    (upcoming ? '<section class="panel" style="border-color:#e0c9a8"><div class="panel-head" style="background:var(--amber-soft)"><h3 style="color:#6d4409">Scheduled change · v' + upcoming.id + '</h3><span class="hint" style="color:#6d4409">effective ' + fmtDateTime(upcoming.effective_from) + "</span></div><div class=\"panel-body\"><div class=\"md\">" +
      md(upcoming.content) + '</div><p class="helper" style="margin-top:10px"><svg class="ico" style="display:inline;vertical-align:-2px"><use href="#i-clock"/></svg> Runs before this moment keep using v' + (active?.id || "—") + '. The scheduler resolves at run time, not at edit time.</p></div></section>' : "") +
    '<section class="panel"><div class="panel-head"><h3>Runs</h3><span class="hint">click a row for evidence</span></div><div class="table-wrap"><table class="data"><thead><tr><th>State</th><th>When</th><th>Instruction</th><th>Evidence</th><th>Delivery</th><th>Error</th></tr></thead><tbody>' +
    (runsTable || '<tr><td colspan="6" class="muted">No runs yet.</td></tr>') + "</tbody></table></div></section>" +
    '<section class="panel"><div class="panel-head"><h3>Instruction history</h3><span class="hint">never edited in place</span></div><div class="table-wrap"><table class="data"><thead><tr><th>Version</th><th>Content</th><th>Effective from</th><th>State</th><th>Supersedes</th></tr></thead><tbody>' +
    (versionsTable || '<tr><td colspan="5" class="muted">—</td></tr>') + "</tbody></table></div></section>" +
    "</div>" +
    '<aside class="stack"><section class="panel"><div class="panel-head"><h3>Last run</h3></div><div class="panel-body">' +
    (c.latest_run ? '<div class="row-wrap">' + chip(c.latest_run.state) + '<span class="tag mono">' + fmtDateTime(c.latest_run.at) + '</span></div><dl class="detail-grid" style="margin-top:12px"><dt>Evidence</dt><dd>' +
      (c.latest_run.evidence?.length ? c.latest_run.evidence.map((e) => esc(e.check_result) + " · " + esc(e.kind)).join("<br>") : "none") + "</dd><dt>Delivery</dt><dd>" +
      (c.latest_run.delivered_at ? "delivered " + fmtDateTime(c.latest_run.delivered_at) : "not delivered") + "</dd><dt>Run id</dt><dd class=\"mono\">" + esc(c.latest_run.id) + "</dd></dl>" +
      (c.latest_run.error ? '<p class="error-text" style="margin-top:10px">' + esc(c.latest_run.error) + "</p>" : "") +
      '<button class="btn btn-sm btn-block" style="margin-top:12px" data-act="open-run" data-id="' + esc(c.latest_run.id) + '">Open evidence</button>'
      : '<p class="muted small">No runs yet.</p>') + "</div></section>" +
    '<section class="panel"><div class="panel-head"><h3>Reliability · 28d</h3></div><div class="panel-body"><div class="row" style="justify-content:space-between"><span class="kpi-value" style="font-size:26px">' +
    pct(c.reliability?.success_rate) + '</span><span class="mono tiny muted">' + (c.reliability?.total || 0) + " runs</span></div><p class=\"helper\" style=\"margin-top:8px\">" +
    (c.reliability?.by_state?.done || 0) + " verified · " + (c.reliability?.by_state?.failed || 0) + " failed · " + (c.reliability?.by_state?.delivery_failed || 0) + " delivery failures. Counts read from the ledger, not the model.</p></div></section>" +
    '<section class="panel"><div class="panel-head"><h3>Verification</h3><span class="hint">' + esc(c.skill) + '</span></div><div class="panel-body"><div class="row-wrap">' +
    ((state.boot.skills.find((s) => s.name === c.skill)?.checks) || ["artifact exists"]).map((check) => '<span class="tag">' + esc(check) + "</span>").join("") +
    '</div><p class="helper" style="margin-top:10px">Checks come from the skill and the instruction version in force. The model cannot mark its own work done.</p></div></section>' +
    "</aside></div>";
}

async function openRunDrawer(runId) {
  openDrawer("Run evidence", '<div class="skeleton" style="height:160px"></div>');
  try {
    const data = await api("/api/runs/" + runId);
    const run = data.run;
    const evidence = (run.evidence || []).map((item) =>
      '<div class="evidence-item"><div class="evidence-head">' + chip(item.check_result === "passed" ? "done" : "failed") +
      "<b>" + esc(item.kind) + '</b><span class="spacer"></span><span class="mono tiny faint">#' + item.id + "</span></div>" +
      '<p class="small" style="margin:6px 0">' + esc(item.summary) + "</p>" +
      '<p class="mono tiny" style="color:var(--muted)">' + esc(item.check_detail) + "</p>" +
      (item.sha256 ? '<p class="hash">sha256 ' + esc(item.sha256) + "</p>" : "") +
      (item.path ? '<p class="hash">' + esc(String(item.path).replace(/^.*?\/data\//, "")) + "</p>" : "") + "</div>").join("");
    $("#drawerBody").innerHTML =
      '<div class="row-wrap">' + chip(run.state) + "<span class=\"tag mono\">" + esc(run.id) + "</span></div>" +
      '<dl class="detail-grid" style="margin-top:14px"><dt>Commitment</dt><dd><a href="#/commitments/' + esc(data.commitment.id) + '">' + esc(data.commitment.title) + "</a></dd>" +
      "<dt>Started</dt><dd>" + fmtDateTime(run.at) + " · " + esc(data.commitment.timezone) + "</dd>" +
      "<dt>Instruction</dt><dd class=\"mono\">v" + run.instruction_version_id + "</dd>" +
      "<dt>Delivery</dt><dd>" + (run.delivered_at ? "delivered " + fmtDateTime(run.delivered_at) : "not delivered") + "</dd>" +
      "<dt>Receipt</dt><dd class=\"mono tiny\">" + esc(JSON.stringify(run.delivery_receipt || {})) + "</dd></dl>" +
      (run.error ? '<p class="error-text" style="margin-top:12px">' + esc(run.error) + "</p>" : "") +
      '<h3 class="section-title" style="margin-top:20px"><span>Evidence</span><span class="hint">deterministic checks</span></h3>' + evidence +
      (data.artifact ? '<h3 class="section-title" style="margin-top:20px"><span>Artifact</span><span class="hint">' + esc(data.commitment.title) + "</span></h3><div class=\"md panel panel-pad\">" + md(data.artifact) + "</div>" : "") +
      '<p class="helper" style="margin-top:16px">“Done” is only produced by the ledger after every evidence item passes. Delivery is recorded separately.</p>';
  } catch (err) {
    $("#drawerBody").innerHTML = '<p class="error-text">' + esc(err.message) + "</p>";
  }
}

/* ------------------------------------------------------------------ memory */

async function renderMemory() {
  const pages = state.boot.pages || [];
  if (!pages.find((p) => p.name === state.memory.page)) state.memory.page = pages[0]?.name || "priorities.md";
  const proposals = state.boot.proposals || [];
  const approvals = state.boot.approvals || [];

  const inbox = proposals.map((p) =>
    '<div class="proposal"><div class="proposal-head"><div style="flex:1"><div class="proposal-title">' + esc(p.title) + '</div><div class="proposal-meta">' + esc(p.page) + " · " + esc(p.kind) + " · " + relTime(p.at) + "</div></div>" +
    '<span class="chip chip-pending"><span class="dot"></span>pending</span></div>' +
    diffHtml(p) +
    '<p class="proposal-reason">' + esc(p.rationale) + (p.source_refs?.length ? " Sources: " + p.source_refs.map((r) => "msg #" + r).join(", ") : "") + "</p>" +
    '<div class="proposal-actions"><button class="btn btn-sm btn-green" data-act="approve-proposal" data-id="' + p.id + '">Approve &amp; write</button>' +
    '<button class="btn btn-sm" data-act="reject-proposal" data-id="' + p.id + '">Reject</button></div></div>').join("");

    const toolApprovals = approvals.map((a) =>
    '<div class="proposal"><div class="proposal-head"><div style="flex:1"><div class="proposal-title">' + esc(a.tool) + ' requested by the agent</div><div class="proposal-meta">' + relTime(a.at) + " · explicit approval required</div></div>" + chip("pending") + "</div>" +
    '<div class="diff"><div class="diff-row add"><span class="diff-mark">+</span><span>' + esc(JSON.stringify(a.args, null, 1)) + "</span></div></div>" +
    '<div class="proposal-actions"><button class="btn btn-sm btn-green" data-act="approve-tool" data-id="' + a.id + '">Approve once</button><button class="btn btn-sm" data-act="deny-tool" data-id="' + a.id + '">Deny</button></div></div>').join("");

  $("#view").innerHTML =
    '<div class="page-head"><div><div class="kicker">Approval inbox · the only write path</div><h1 class="display">Memory</h1>' +
    '<p class="page-sub">Markdown you can read and edit. Chat reads this store; consolidation proposes additions; only your decision writes them.</p></div>' +
    '<button class="btn" data-act="consolidate"><svg class="ico"><use href="#i-refresh"/></svg>Consolidate now</button></div>' +
    '<div class="split"><div class="stack">' +
    '<section class="panel"><div class="panel-head"><h3>Pending proposals</h3><span class="hint">' + proposals.length + " waiting · " + approvals.length + " tool approval" + (approvals.length === 1 ? "" : "s") + "</span></div>" +
    (inbox + toolApprovals || '<div class="need-empty"><strong>Nothing waiting.</strong>Consolidation found no new durable facts.</div>') + "</section>" +
    '<section class="panel" id="pagePanel"><div class="panel-head"><h3 id="pageTitle">' + esc(state.memory.page) + '</h3><span class="hint" id="pageMeta">loading…</span></div><div class="panel-body" id="pageBody"><div class="skeleton" style="height:200px"></div></div></section>' +
    "</div>" +
    '<aside class="stack"><section class="panel"><div class="panel-head"><h3>Pages</h3></div><div style="padding:8px">' +
    pages.map((p) => '<button class="mem-page-btn ' + (p.name === state.memory.page ? "active" : "") + '" data-act="memory-page" data-page="' + esc(p.name) + '">' +
      esc(p.title || p.name) + "<small>" + esc(p.name) + " · " + (p.updated ? relTime(p.updated) : "no date") + "</small></button>").join("") +
    "</div></section>" +
    '<section class="panel"><div class="panel-head"><h3>Why this is safe</h3></div><div class="panel-body"><p class="helper">Consolidation reads the last 24h window and proposes facts with source message ids. Approval appends a bullet; rejection leaves the page untouched. Every decision is audited. Chat never writes here.</p></div></section>' +
    "</aside></div>";
  loadPage();
}

function diffHtml(proposal) {
  const strip = (line) => line.trim().replace(/^[-*+]\s+/, "").replace(/^\d+\.\s+/, "");
  const before = String(proposal.before || "").split("\n").map(strip).filter(Boolean);
  const after = String(proposal.after || "").split("\n").map(strip).filter(Boolean);
  const beforeSet = new Set(before);
  const added = after.filter((l) => !beforeSet.has(l));
  const context = before.slice(-2);
  const cell = (line) => "<span>" + inline(esc(line)) + "</span>";
  const rows = context.map((l) => '<div class="diff-row ctx"><span class="diff-mark">·</span>' + cell(l) + "</div>").join("") +
    (added.length ? added.map((l) => '<div class="diff-row add"><span class="diff-mark">+</span>' + cell(l) + "</div>").join("") : '<div class="diff-row ctx"><span class="diff-mark">·</span><span>(no change)</span></div>');
  return '<div class="diff"><div class="diff-head">Memory page preview · ' + (added.length || 0) + " line" + (added.length === 1 ? "" : "s") + " appended</div>" + rows + "</div>";
}

async function loadPage(force = false) {
  const name = state.memory.page;
  const holder = $("#pageBody");
  if (!holder) return;
  let data = state.memory.cache[name];
  try {
    if (!data || force) {
      data = await api("/api/memory/" + encodeURIComponent(name));
      state.memory.cache[name] = data;
    }
    const meta = data.frontmatter || {};
    $("#pageTitle").textContent = meta.title || name;
    $("#pageMeta").textContent = (meta.updated ? "updated " + relTime(meta.updated) : "no timestamp") + " · " + (data.body || "").length + " chars";
    holder.innerHTML = state.memory.editing
      ? '<div class="editor"><textarea id="pageEditor" aria-label="Edit ' + esc(name) + '">' + esc(data.body || "") + "</textarea>" +
        '<div class="form-actions"><button class="btn" data-act="cancel-edit">Cancel</button><button class="btn btn-green" data-act="save-memory">Save page</button></div></div>'
      : '<div class="md">' + md(data.body || "") + '</div><div class="row" style="margin-top:14px;border-top:1px solid var(--line-soft);padding-top:12px"><span class="tag mono">' + esc(name) + '</span><span class="spacer"></span><button class="btn btn-sm" data-act="edit-memory">Edit</button></div>';
  } catch (err) {
    holder.innerHTML = '<p class="error-text">' + esc(err.message) + "</p>";
  }
}

/* ------------------------------------------------------------------ skills */

function renderSkills() {
  const skills = state.boot.skills || [];
  const tools = state.boot.tools || [];
  const policy = state.boot.policy || {};

  const skillCards = skills.map((s) =>
    '<article class="panel skill-card"><div class="row" style="justify-content:space-between"><h3>' + esc(s.title) + '</h3><span class="skill-status ' + (s.status === "beta" ? "beta" : "") + '">' + esc(s.status) + "</span></div>" +
    '<p class="mono tiny muted">' + esc(s.name) + "</p><p>" + esc(s.description) + "</p>" +
    '<div class="checks"><span class="tag">tools: ' + esc(s.tools.join(", ")) + "</span>" + s.checks.map((c) => '<span class="tag">' + esc(c) + "</span>").join("") + "</div></article>").join("");

  const toolRows = tools.map((t) =>
    "<tr><td><div class=\"cell-strong\">" + esc(t.name) + "</div><div class=\"cell-sub\">" + esc(t.description) + "</div></td>" +
    "<td>" + riskTag(t.risk) + "</td><td>" + (t.requires_approval ? '<span class="chip chip-delivery"><span class="dot"></span>approval</span>' : '<span class="chip chip-done"><span class="dot"></span>allowlisted</span>') + "</td>" +
    "<td>" + (t.egress.length ? t.egress.map((e) => '<span class="tag">' + esc(e) + "</span>").join(" ") : '<span class="muted tiny">local</span>') + "</td></tr>").join("");

  $("#view").innerHTML =
    '<div class="page-head"><div><div class="kicker">Reusable behaviour</div><h1 class="display">Skills &amp; tools</h1>' +
    '<p class="page-sub">A skill is an inspectable unit: <span class="inline-code">execute()</span> writes an artifact, <span class="inline-code">verify()</span> owns the rules. A tool is the only door to the outside world, and policy guards it.</p></div></div>' +
    '<div class="skill-grid">' + skillCards + "</div>" +
    '<section class="panel" style="margin-top:20px"><div class="panel-head"><h3>Governed tools</h3><span class="hint">deny by default · audit every decision</span></div><div class="table-wrap"><table class="data"><thead><tr><th>Tool</th><th>Risk</th><th>Gate</th><th>Egress</th></tr></thead><tbody>' + toolRows + "</tbody></table></div></section>" +
    '<div class="split" style="margin-top:20px"><section class="panel"><div class="panel-head"><h3>Egress allowlist</h3><span class="hint">HTTPS · exact host</span></div><div class="panel-body"><div class="allowlist">' +
    (policy.egress_allowlist || []).map((h) => "<code>" + esc(h) + "</code>").join("") + '</div><p class="helper" style="margin-top:12px">A single HTTP wrapper checks scheme, host and private-address resolution before a byte leaves the process. Redirects are not followed.</p></div></section>' +
    '<section class="panel"><div class="panel-head"><h3>Tavily</h3><span class="hint">runtime web research</span></div><div class="panel-body"><p class="helper">' +
    (state.boot.tavily ? "Tavily is configured; research_digest makes live calls and verification requires two sources with URLs." : "No Tavily key on this instance. The tool returns a clearly labelled cached demo lane rather than pretending to search.") +
    "</p></div></section></div>";
}

/* ------------------------------------------------------------------- audit */

async function renderAudit() {
  $("#view").innerHTML =
    '<div class="page-head"><div><div class="kicker">No hidden actions</div><h1 class="display">Audit</h1>' +
    '<p class="page-sub">Every tool decision, approval and model call lands here. Denied attempts are kept, not discarded — they are the evidence that the allowlist does something.</p></div></div>' +
    '<div class="tabs"><button class="tab ' + (state.audit.tab === "decisions" ? "active" : "") + '" data-act="audit-tab" data-tab="decisions">Decisions</button><button class="tab ' + (state.audit.tab === "calls" ? "active" : "") + '" data-act="audit-tab" data-tab="calls">Model calls</button></div>' +
    '<div id="auditBody"><div class="skeleton" style="height:220px"></div></div>';
  await loadAudit();
}

async function loadAudit() {
  const holder = $("#auditBody");
  if (!holder) return;
  try {
    if (!state.audit.rows) {
      const data = await api("/api/audit?limit=150");
      state.audit.rows = data.audit || [];
      state.audit.calls = data.calls || [];
    }
    if (state.audit.tab === "calls") {
      holder.innerHTML = '<section class="panel"><div class="panel-head"><h3>Model calls</h3><span class="hint">persisted cost, not an estimate from prose</span></div><div class="table-wrap"><table class="data"><thead><tr><th>When</th><th>Provider</th><th>Purpose</th><th>Model</th><th>Latency</th><th>Tokens</th><th class="right">Cost</th></tr></thead><tbody>' +
        (state.audit.calls || []).map((c) =>
          '<tr><td class="mono">' + fmtDateTime(c.at) + "</td><td>" + esc(c.provider) + '</td><td class="mono">' + esc(c.purpose) + "</td><td class=\"mono tiny\">" + esc(c.model) + "</td><td class=\"mono\">" + c.latency_s.toFixed(2) + "s</td><td class=\"mono\">" + c.prompt_tokens + " / " + c.completion_tokens + "</td><td class=\"right mono\">" + money(c.cost_usd) + "</td></tr>").join("") +
        "</tbody></table></div></section>";
      return;
    }
    const filters = ["all", "allowed", "denied", "approval_required"];
    const rows = (state.audit.rows || []).filter((r) => state.audit.filter === "all" || r.decision === state.audit.filter);
    holder.innerHTML = '<div class="row-wrap" style="margin-bottom:12px">' + filters.map((f) =>
      '<button class="btn btn-sm ' + (state.audit.filter === f ? "btn-primary" : "") + '" data-act="audit-filter" data-filter="' + f + '">' + f.replace("_", " ") + "</button>").join("") + "</div>" +
      '<section class="panel"><div class="panel-head"><h3>Decisions</h3><span class="hint">' + rows.length + " shown</span></div><div class=\"table-wrap\"><table class=\"data\"><thead><tr><th>When</th><th>Action</th><th class=\"col-target\">Target</th><th>Decision</th><th class=\"col-risk\">Risk</th><th class=\"col-actor\">Actor</th><th>Detail</th></tr></thead><tbody>" +
      rows.map((r) =>
        '<tr><td class="mono">' + fmtDateTime(r.at) + "</td><td class=\"mono\">" + esc(r.action) + '</td><td class="mono tiny col-target">' + esc(r.target || "—") + "</td><td>" + decisionChip(r.decision) + '</td><td class="col-risk">' + riskTag(r.risk) + '</td><td class="mono tiny col-actor">' + esc(r.actor) + "</td><td>" +
        (r.detail ? '<details class="json"><summary><span>View</span><svg class="ico"><use href="#i-chevron"/></svg></summary><pre>' + esc(JSON.stringify(r.detail, null, 2)) + "</pre></details>" : '<span class="faint">—</span>') + "</td></tr>").join("") +
      "</tbody></table></div></section>";
  } catch (err) {
    holder.innerHTML = '<p class="error-text">' + esc(err.message) + "</p>";
  }
}

/* ------------------------------------------------------------------- stats */

async function renderStats() {
  $("#view").innerHTML =
    '<div class="page-head"><div><div class="kicker">Net benefit, measured</div><h1 class="display">Stats</h1>' +
    '<p class="page-sub">Routing keeps personal-volume cost in the single-digit dollars per month. Reliability is counted from run states; interventions count the times you had to step in.</p></div>' +
    '<div class="row"><button class="btn btn-sm ' + (state.stats.days === 7 ? "btn-primary" : "") + '" data-act="stats-days" data-days="7">7 days</button><button class="btn btn-sm ' + (state.stats.days === 30 ? "btn-primary" : "") + '" data-act="stats-days" data-days="30">30 days</button></div></div>' +
    '<div id="statsBody"><div class="skeleton" style="height:240px"></div></div>';
  try {
    const data = await api("/api/stats?days=" + state.stats.days);
    state.stats.data = data;
    renderStatsBody(data);
  } catch (err) {
    $("#statsBody").innerHTML = '<p class="error-text">' + esc(err.message) + "</p>";
  }
}

function renderStatsBody(data) {
  const usage = data.usage;
  const runs = data.runs;
  const interventions = data.interventions;
  const purposes = usage.by_purpose || [];
  const maxCost = Math.max(0.0001, ...purposes.map((p) => p.cost));
  const colors = { chat: "", fast: "amber", reasoning: "blue" };
  const bars = purposes.map((p) =>
    '<div class="bar-row"><span class="mono tiny">' + esc(p.purpose) + '</span><div class="bar-track"><div class="bar-fill ' + (colors[p.purpose] || "") + '" style="width:' + Math.max(2, (p.cost / maxCost) * 100) + '%"></div></div><span class="bar-value">' + money(p.cost) + "<small>" + p.calls + " calls</small></span></div>").join("");

  const days = buildDays(usage.by_day || [], state.stats.days);
  const rawMax = Math.max(0.0001, ...days.map((d) => d.cost));
  const max = niceCeil(rawMax);
  const compact = window.innerWidth < 700;
  const w = compact ? 360 : 720;
  const h = compact ? 168 : 176;
  const pad = { l: compact ? 40 : 46, r: compact ? 12 : 16, t: 12, b: 26 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const xAt = (i) => pad.l + (days.length > 1 ? (i / (days.length - 1)) * iw : iw / 2);
  const yAt = (v) => pad.t + ih - (v / max) * ih;
  const path = days.map((d, i) => (i === 0 ? "M" : "L") + xAt(i).toFixed(1) + " " + yAt(d.cost).toFixed(1)).join(" ");
  const area = path + " L " + xAt(days.length - 1).toFixed(1) + " " + (pad.t + ih) + " L " + pad.l + " " + (pad.t + ih) + " Z";
  const ticks = [0, 0.5, 1].map((t) => {
    const value = max * t;
    const y = yAt(value);
    return '<line class="gridline" x1="' + pad.l + '" y1="' + y + '" x2="' + (w - pad.r) + '" y2="' + y + '"/>' +
      '<text x="' + (pad.l - 8) + '" y="' + (y + 3) + '" text-anchor="end">' + money(value) + "</text>";
  }).join("");
  const step = Math.max(1, Math.ceil(days.length / (compact ? 4 : 6)));
  const labels = days.map((d, i) => {
    if (i % step !== 0 && i !== days.length - 1) return "";
    const anchor = i === 0 ? "start" : i === days.length - 1 ? "end" : "middle";
    return '<text x="' + xAt(i) + '" y="' + (pad.t + ih + 16) + '" text-anchor="' + anchor + '">' + esc(d.label) + "</text>";
  }).join("");
  const last = days[days.length - 1];
  const endpoint = '<circle class="endpoint" cx="' + xAt(days.length - 1) + '" cy="' + yAt(last.cost) + '" r="3"/>';
  const chart =
    '<svg class="chart" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Daily inference cost over ' + state.stats.days + ' days">' +
    ticks + '<path class="area" d="' + area + '"/><path class="line" d="' + path + '"/>' + endpoint + labels + "</svg>";

  const stateRows = Object.entries(runs.by_state || {}).map(([k, v]) =>
    '<div class="bar-row"><span class="mono tiny">' + esc(k) + '</span><div class="bar-track"><div class="bar-fill ' + (k === "done" ? "" : k === "failed" ? "red" : "amber") + '" style="width:' + Math.max(2, (v / Math.max(1, runs.total)) * 100) + '%"></div></div><span class="bar-value">' + v + "</span></div>").join("");

  const models = (usage.by_model || []).map((m) =>
    '<tr><td><div class="mono tiny model-id">' + esc(m.model) + '</div><div class="cell-sub">' + esc(m.provider) + "</div></td><td class=\"mono\">" + m.calls + "</td><td class=\"right mono\">" + money(m.cost) + "</td></tr>").join("");

  $("#statsBody").innerHTML =
    '<div class="stat-strip">' +
    kpi("Inference cost", money(usage.cost_usd), "", usage.calls + " calls · " + (usage.avg_latency_s || 0).toFixed(2) + "s avg", "accent-green") +
    kpi("Verified runs", pct(runs.success_rate), "", (runs.total || 0) + " runs · " + (runs.failed || 0) + " failed", runs.success_rate >= 0.8 ? "accent-green" : "accent-amber") +
    kpi("Delivery failures", String(runs.delivery_failed || 0), "", "surfaced without asking", runs.delivery_failed ? "accent-amber" : "accent-green") +
    kpi("Interventions", String((interventions.memory_decisions || 0) + (interventions.tool_approvals || 0) + (interventions.manual_runs || 0)), "", "decisions you had to make", "accent-amber") +
    "</div>" +
    '<div class="split" style="margin-top:20px"><div class="stack">' +
    '<section class="panel"><div class="panel-head"><h3>Inference spend</h3><span class="hint">' + state.stats.days + ' days · stored per call</span></div><div class="panel-body">' + chart + "</div></section>" +
    '<section class="panel"><div class="panel-head"><h3>Cost by purpose</h3><span class="hint">routing is visible</span></div><div class="panel-body"><div class="bars">' + (bars || '<p class="muted small">No calls in this window.</p>') + '</div><div class="legend"><span><i style="background:var(--green)"></i>chat</span><span><i style="background:var(--amber)"></i>fast</span><span><i style="background:var(--blue)"></i>reasoning</span></div></div></section>' +
    "</div><aside class=\"stack\">" +
    '<section class="panel"><div class="panel-head"><h3>Reliability</h3><span class="hint">run states</span></div><div class="panel-body"><div class="bars">' + (stateRows || '<p class="muted small">No runs.</p>') + '</div><p class="helper" style="margin-top:10px">A run reaches “done” only after every evidence item passes its check.</p></div></section>' +
    '<section class="panel"><div class="panel-head"><h3>Interventions</h3><span class="hint">O4 counter</span></div><div class="panel-body"><dl class="detail-grid"><dt>Memory</dt><dd>' + (interventions.memory_decisions || 0) + " decision" + (interventions.memory_decisions === 1 ? "" : "s") + "</dd><dt>Tool approvals</dt><dd>" + (interventions.tool_approvals || 0) + "</dd><dt>Manual runs</dt><dd>" + (interventions.manual_runs || 0) + "</dd></dl><p class=\"helper\" style=\"margin-top:10px\">Compared with the W1 baseline, where every verification was manual.</p></div></section>" +
    '<section class="panel"><div class="panel-head"><h3>By model</h3></div><div class="table-wrap"><table class="data"><thead><tr><th>Model</th><th>Calls</th><th class="right">Cost</th></tr></thead><tbody>' + (models || '<tr><td colspan="3" class="muted">—</td></tr>') + "</tbody></table></div></section>" +
    "</aside></div>";
}

function niceCeil(value) {
  if (!value || value <= 0) return 0.01;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const scaled = value / magnitude;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * magnitude;
}

function buildDays(byDay, count) {  const map = new Map(byDay.map((d) => [d.day, d]));
  const out = [];
  const now = new Date();
  for (let i = count - 1; i >= 0; i -= 1) {
    const date = new Date(now.getTime() - i * 86400000);
    const key = date.toISOString().slice(0, 10);
    const row = map.get(key) || { day: key, calls: 0, cost: 0 };
    out.push({ ...row, label: key.slice(5) });
  }
  return out;
}

/* ------------------------------------------------------------------ drawer */

function openDrawer(title, html) {
  $("#drawerTitle").textContent = title;
  $("#drawerBody").innerHTML = html;
  $("#drawer").hidden = false;
  $("#drawerScrim").hidden = false;
  $("#drawerClose").focus();
}

function closeDrawer() {
  $("#drawer").hidden = true;
  $("#drawerScrim").hidden = true;
}

function openDialog(title, html, onSubmit) {
  $("#dialogTitle").textContent = title;
  $("#dialogBody").innerHTML = html;
  $("#dialog").hidden = false;
  $("#dialogClose").focus();
  const form = $("#dialogBody form");
  if (form && onSubmit) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button[type=submit]");
      await withBusy(button, async () => {
        try {
          await onSubmit(new FormData(form));
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
  }
  const first = $("#dialogBody input, #dialogBody textarea, #dialogBody select");
  if (first) first.focus();
}

function closeDialog() {
  $("#dialog").hidden = true;
}

/* ------------------------------------------------------------------ forms */

function newCommitmentDialog() {
  const skills = (state.boot.skills || []).map((s) => '<option value="' + esc(s.name) + '">' + esc(s.title) + "</option>").join("");
  openDialog(
    "New commitment",
    '<form><div class="form-grid">' +
      '<div class="field full"><label for="f-title">Title</label><input id="f-title" name="title" required placeholder="e.g. Morning research brief"></div>' +
      '<div class="field"><label for="f-schedule">Daily time</label><input id="f-schedule" name="schedule" value="07:00" pattern="[0-2][0-9]:[0-5][0-9]" required><span class="help">24h local time, evaluated in the timezone.</span></div>' +
      '<div class="field"><label for="f-channel">Delivery</label><select id="f-channel" name="delivery_channel"><option value="outbox">outbox (local)</option><option value="ntfy">ntfy push</option><option value="telegram">Telegram (optional)</option></select></div>' +
      '<div class="field"><label for="f-skill">Skill</label><select id="f-skill" name="skill">' + skills + "</select></div>" +
      '<div class="field"><label for="f-max">Max words</label><input id="f-max" name="max_words" type="number" value="180" min="40" max="600"></div>' +
      '<div class="field full"><label for="f-instruction">Instruction (version 1)</label><textarea id="f-instruction" name="instruction" required placeholder="What should run, and what does a good result look like?"></textarea><span class="help">This becomes instruction v1, approved now and effective immediately.</span></div>' +
    '</div><div class="form-actions"><button type="button" class="btn" data-act="close-dialog">Cancel</button><button type="submit" class="btn btn-green">Create commitment</button></div></form>',
    async (form) => {
      const payload = {
        title: form.get("title"),
        schedule: form.get("schedule"),
        delivery_channel: form.get("delivery_channel"),
        skill: form.get("skill"),
        timezone: state.boot.app.timezone,
        instruction: form.get("instruction"),
        params: { max_words: Number(form.get("max_words") || 180) },
      };
      const created = await api("/api/commitments", { method: "POST", body: JSON.stringify(payload) });
      closeDialog();
      toast("Commitment created with instruction v1.");
      state.boot = await api("/api/bootstrap");
      updateShell();
      location.hash = "#/commitments/" + created.id;
    }
  );
}

function newInstructionDialog(id) {
  openDialog(
    "New instruction version",
    '<form><div class="form-grid">' +
      '<div class="field full"><label for="f-content">Instruction</label><textarea id="f-content" name="content" required placeholder="The new wording. The old version is kept in history."></textarea></div>' +
      '<div class="field"><label for="f-effective">Effective from</label><input id="f-effective" name="effective_from" type="datetime-local" required></div>' +
      '<div class="field"><label for="f-max">Max words</label><input id="f-max" name="max_words" type="number" value="180" min="40" max="600"></div>' +
    '</div><p class="helper" style="margin-top:10px">Pick tomorrow to demo version truth: today’s runs still resolve the current version.</p><div class="form-actions"><button type="button" class="btn" data-act="close-dialog">Cancel</button><button type="submit" class="btn btn-green">Approve &amp; schedule</button></div></form>',
    async (form) => {
      const local = new Date(form.get("effective_from"));
      const payload = {
        content: form.get("content"),
        effective_from: local.toISOString(),
        params: { max_words: Number(form.get("max_words") || 180) },
      };
      await api("/api/commitments/" + id + "/instructions", { method: "POST", body: JSON.stringify(payload) });
      closeDialog();
      toast("Instruction version appended.");
      state.boot = await api("/api/bootstrap");
      updateShell();
      renderCommitmentDetail(id);
    }
  );
}

/* ----------------------------------------------------------------- actions */

document.addEventListener("click", async (event) => {
  const el = event.target.closest("[data-act]");
  if (!el) return;
  const act = el.dataset.act;
  const id = el.dataset.id;

  if (act === "session") { closeDrawer(); await openSession(id); return; }
  if (act === "new-chat") {
    closeDrawer();
    state.chat.draft = true;
    state.chat.sessionId = null; state.chat.messages = []; state.chat.sources = []; state.chat.trace = [];
    await renderChat(); return;
  }
  if (act === "chat-sessions") {
    openDrawer("Conversations",
      '<div class="stack-sm">' + (state.boot.sessions || []).map((s) =>
        '<button class="btn btn-block" style="justify-content:flex-start" data-act="session" data-id="' + esc(s.id) + '">' +
        esc(s.title) + "</button>").join("") + "</div>" +
      '<button class="btn btn-primary btn-block" style="margin-top:12px" data-act="new-chat">New conversation</button>');
    return;
  }
  if (act === "suggest") { await sendChat(el.dataset.text); return; }
  if (act === "open-commitment") { location.hash = "#/commitments/" + id; return; }
  if (act === "open-run") { await openRunDrawer(id); return; }
  if (act === "new-commitment") { newCommitmentDialog(); return; }
  if (act === "close-dialog" || act === "dialog-close") { closeDialog(); return; }
  if (act === "new-instruction") { newInstructionDialog(id); return; }
  if (act === "memory-page") {
    state.memory.page = el.dataset.page; state.memory.editing = false;
    await renderMemory(); return;
  }
  if (act === "edit-memory") { state.memory.editing = true; await loadPage(); $("#pageEditor")?.focus(); return; }
  if (act === "cancel-edit") { state.memory.editing = false; await loadPage(); return; }
  if (act === "save-memory") {
    const body = $("#pageEditor")?.value ?? "";
    await withBusy(el, async () => {
      try {
        await api("/api/memory/" + encodeURIComponent(state.memory.page), { method: "PUT", body: JSON.stringify({ body }) });
        state.memory.editing = false;
        state.memory.cache[state.memory.page] = null;
        toast("Memory page saved.");
        state.boot = await api("/api/bootstrap");
        updateShell();
        await loadPage(true);
      } catch (err) { toast(err.message, "error"); }
    });
    return;
  }
  if (act === "audit-tab") { state.audit.tab = el.dataset.tab; await renderAudit(); return; }
  if (act === "audit-filter") { state.audit.filter = el.dataset.filter; await loadAudit(); return; }
  if (act === "stats-days") { state.stats.days = Number(el.dataset.days); await renderStats(); return; }
  if (act === "notice") {
    const notice = (state.boot.notices || []).find((n) => n.name === id);
    openDrawer("Fallback notice", '<div class="md">' + md(notice?.body || "") + "</div>");
    return;
  }
  if (act === "approve-proposal" || act === "reject-proposal") {
    await withBusy(el, async () => {
      try {
        const decision = act === "approve-proposal" ? "approved" : "rejected";
        await api("/api/proposals/" + id + "/decide", { method: "POST", body: JSON.stringify({ decision }) });
        toast(decision === "approved" ? "Written to the self-model." : "Proposal rejected; page untouched.");
        state.memory.cache = {};
        state.boot = await api("/api/bootstrap");
        updateShell();
        route();
      } catch (err) { toast(err.message, "error"); }
    });
    return;
  }
  if (act === "approve-tool" || act === "deny-tool") {
    await withBusy(el, async () => {
      try {
        const decision = act === "approve-tool" ? "approved" : "denied";
        const result = await api("/api/approvals/" + id + "/decide", { method: "POST", body: JSON.stringify({ decision }) });
        toast(decision === "approved" ? (result.result?.ok ? "Approved and executed." : "Approved, but the tool failed.") : "Denied.");
        state.boot = await api("/api/bootstrap");
        updateShell();
        route();
      } catch (err) { toast(err.message, "error"); }
    });
    return;
  }
  if (act === "consolidate") {
    await withBusy(el, async () => {
      try {
        const result = await api("/api/consolidate", { method: "POST", body: "{}" });
        toast(result.created.length + " proposal(s) · " + result.method + " lane");
        state.boot = await api("/api/bootstrap");
        updateShell();
        route();
      } catch (err) { toast(err.message, "error"); }
    });
    return;
  }
  if (act === "run-now") {
    await withBusy(el, async () => {
      try {
        const result = await api("/api/commitments/" + id + "/run", { method: "POST", body: "{}" });
        const stateName = result.outcome.state;
        toast(stateName === "done" ? "Run verified and delivered." : "Run ended as " + stateName + " — see the run detail.",
          stateName === "done" ? "ok" : "error");
        state.boot = await api("/api/bootstrap");
        updateShell();
        await renderCommitmentDetail(id);
        if (result.outcome.run_id) await openRunDrawer(result.outcome.run_id);
      } catch (err) { toast(err.message, "error"); }
    });
    return;
  }
  if (act === "toggle-state") {
    await withBusy(el, async () => {
      try {
        await api("/api/commitments/" + id + "/state", { method: "POST", body: JSON.stringify({ state: el.dataset.state }) });
        toast("Commitment " + el.dataset.state + ".");
        state.boot = await api("/api/bootstrap");
        updateShell();
        await renderCommitmentDetail(id);
      } catch (err) { toast(err.message, "error"); }
    });
    return;
  }
});

/* ------------------------------------------------------------------ overlays */

$("#drawerClose").addEventListener("click", closeDrawer);
$("#drawerScrim").addEventListener("click", closeDrawer);
$("#dialogClose").addEventListener("click", closeDialog);
$("#dialog").addEventListener("click", (event) => { if (event.target.id === "dialog") closeDialog(); });
$("#refreshBtn").addEventListener("click", async () => {
  state.boot = await api("/api/bootstrap");
  state.audit.rows = null; state.stats.data = null;
  updateShell();
  route();
  toast("Refreshed from the ledger.");
});
$("#newCommitmentTop").addEventListener("click", newCommitmentDialog);
$("#resetDemo").addEventListener("click", async () => {
  if (!confirm("Reset the synthetic demo data?")) return;
  await api("/api/demo/reset", { method: "POST", body: "{}" });
  toast("Demo data reseeded.");
  location.hash = "#/today";
  location.reload();
});
$("#menuBtn").addEventListener("click", () => {
  const rail = $("#rail");
  const open = rail.classList.toggle("open");
  $("#railScrim").hidden = !open;
  $("#menuBtn").setAttribute("aria-expanded", String(open));
});
$("#railScrim").addEventListener("click", () => {
  $("#rail").classList.remove("open");
  $("#railScrim").hidden = true;
  $("#menuBtn").setAttribute("aria-expanded", "false");
});

/* ------------------------------------------------------------------ palette */

const views = [
  ["Today", "#/today", "view"], ["Chat", "#/chat", "view"], ["Commitments", "#/commitments", "view"],
  ["Memory", "#/memory", "view"], ["Skills & tools", "#/skills", "view"], ["Audit", "#/audit", "view"], ["Stats", "#/stats", "view"],
];

function paletteItems(query) {
  const q = query.trim().toLowerCase();
  const items = [];
  for (const [label, href, kind] of views) items.push({ label, href, kind });
  for (const c of state.boot?.commitments || []) items.push({ label: c.title, href: "#/commitments/" + c.id, kind: "commitment" });
  for (const p of state.boot?.pages || []) items.push({ label: p.title || p.name, href: "#/memory", kind: "memory", page: p.name });
  return items.filter((i) => !q || i.label.toLowerCase().includes(q)).slice(0, 9);
}

function renderPalette(query) {
  const list = $("#paletteList");
  const items = paletteItems(query);
  list.innerHTML = items.map((item, index) =>
    '<li role="option" aria-selected="false"><button data-palette="' + index + '" class="' + (index === 0 ? "sel" : "") + '"><svg class="ico"><use href="#i-' +
    (item.kind === "commitment" ? "commit" : item.kind === "memory" ? "memory" : "arrow") + '"/></svg>' + esc(item.label) +
    '<span class="p-kind">' + esc(item.kind) + "</span></button></li>").join("") || '<li><button disabled>No matches</button></li>';
  list.dataset.items = JSON.stringify(items);
}

function openPalette() {
  $("#palette").hidden = false;
  $("#paletteInput").value = "";
  renderPalette("");
  $("#paletteInput").focus();
}

function closePalette() { $("#palette").hidden = true; }

$("#paletteBtn").addEventListener("click", openPalette);

$("#paletteInput").addEventListener("input", (event) => renderPalette(event.target.value));
$("#paletteInput").addEventListener("keydown", (event) => {
  if (event.key === "Escape") { closePalette(); return; }
  if (event.key === "Enter") {
    const sel = $("#paletteList .sel")?.closest("li")?.querySelector("button");
    (sel || $("#paletteList button"))?.click();
  }
});
$("#paletteList").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-palette]");
  if (!button) return;
  const items = JSON.parse($("#paletteList").dataset.items || "[]");
  const item = items[Number(button.dataset.palette)];
  if (!item) return;
  if (item.page) { state.memory.page = item.page; }
  closePalette();
  location.hash = item.href;
});
$("#palette").addEventListener("click", (event) => { if (event.target.id === "palette") closePalette(); });

document.addEventListener("keydown", (event) => {
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault(); openPalette(); return;
  }
  if (event.key === "/" && !typing) { event.preventDefault(); openPalette(); return; }
  if (event.key === "Escape") {
    closePalette();
    closeDialog();
    closeDrawer();
    $("#rail").classList.remove("open");
    $("#railScrim").hidden = true;
  }
});

/* -------------------------------------------------------------------- start */

window.addEventListener("hashchange", route);
boot();
