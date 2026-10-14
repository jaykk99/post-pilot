/* Post Pilot dashboard. Drafts need Jay's tap: approve -> publish. */
let CODE = localStorage.getItem("pp_code") || "";
let STATE = null;

const $ = (s) => document.querySelector(s);
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.style.display = "block";
  setTimeout(() => (t.style.display = "none"), 2600);
}
async function api(path, opts = {}) {
  const headers = Object.assign({"Content-Type": "application/json"}, opts.headers || {});
  if (CODE) headers["X-Access-Code"] = CODE;
  const sep = path.includes("?") ? "&" : "?";
  const res = await fetch(path + (CODE ? sep + "code=" + encodeURIComponent(CODE) : ""),
    Object.assign({headers}, opts));
  if (res.status === 401) { showGate(); throw new Error("locked"); }
  return res.json();
}
function showGate() { $("#authGate").classList.remove("hidden"); $("#board").innerHTML = ""; }
function hideGate() { $("#authGate").classList.add("hidden"); }

function statusChip(d) {
  return `<span class="status ${d.status}">${d.status.replace("_", " ")}</span>`;
}
function targetChips(b) {
  return b.targets.map((t) => {
    const cls = t.id ? "live" : "dead";
    const label = t.id ? `${t.platform}: connected` : `${t.platform}: ${t.note || "skipped"}`;
    return `<span class="tgt ${cls}">${label}</span>`;
  }).join("");
}
function metricsLine(b) {
  if (!b.metrics || !b.metrics.length) return `<div class="metrics">no metrics yet</div>`;
  const m = b.metrics[0];
  return `<div class="metrics">latest sample: ${m.views} views / ${m.reach} reach (${m.target})</div>`;
}
function draftCard(b, d) {
  const canApprove = d.status === "draft";
  const canPublish = d.status === "approved";
  const pubs = [];
  if (b.targets.find((t) => t.platform === "facebook" && t.id))
    pubs.push(`<button data-act="publish" data-platform="facebook" ${canPublish ? "" : "disabled"}>Publish to FB</button>`);
  if (b.targets.find((t) => t.platform === "instagram" && t.id))
    pubs.push(`<button data-act="publish" data-platform="instagram" ${canPublish ? "" : "disabled"}>Publish to IG</button>`);
  return `<div class="draft" data-id="${d.id}">
    ${d.image_url ? `<img src="${d.image_url}" loading="lazy" alt="">` : ""}
    <div class="body">
      ${statusChip(d)}
      <div class="theme">${esc(d.angle_theme)}</div>
      <div class="caption" id="cap-${d.id}">${esc(d.caption)}</div>
      <div class="tags">${esc(d.hashtags.join(" "))}</div>
      <div class="meta">suggested post time: ${esc(d.post_time)}${d.reviewer_notes ? " &middot; " + esc(d.reviewer_notes) : ""}</div>
    </div>
    <div class="actions">
      <button data-act="approve" class="ok" ${canApprove ? "" : "disabled"}>Approve</button>
      <button data-act="reject" class="bad" ${canApprove ? "" : "disabled"}>Reject</button>
      <button data-act="edit">Edit</button>
      ${pubs.join("")}
    </div>
  </div>`;
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}
function render() {
  const board = $("#board");
  board.innerHTML = STATE.businesses.map((b) => `
    <section class="biz">
      <div class="biz-head">
        <h2>${esc(b.name)}</h2>
        <div class="tag">${esc(b.tagline)}</div>
        <div class="targets">${targetChips(b)}</div>
        ${metricsLine(b)}
      </div>
      ${b.drafts.length
        ? `<div class="drafts">${b.drafts.map((d) => draftCard(b, d)).join("")}</div>`
        : `<div class="empty">No drafts yet today. Hit "Generate today's drafts".</div>`}
    </section>`).join("");
  board.querySelectorAll("button[data-act]").forEach((btn) =>
    btn.addEventListener("click", () => handleAction(btn)));
}
async function handleAction(btn) {
  const card = btn.closest(".draft");
  const id = card.dataset.id;
  const act = btn.dataset.act;
  btn.disabled = true;
  try {
    if (act === "approve" || act === "reject") {
      await api(`/api/drafts/${id}/${act}`, {method: "POST"});
      toast(act === "approve" ? "Approved. Publish when ready." : "Rejected.");
    } else if (act === "edit") {
      const cap = card.querySelector(".caption");
      const ta = document.createElement("textarea");
      ta.className = "editbox"; ta.value = cap.textContent;
      cap.replaceWith(ta);
      btn.textContent = "Save";
      btn.dataset.act = "save";
      btn.disabled = false;
      return;
    } else if (act === "save") {
      const ta = card.querySelector(".editbox");
      const r = await api(`/api/drafts/${id}/edit`, {method: "POST",
        body: JSON.stringify({caption: ta.value})});
      toast(r.review_pass ? "Saved. Review passed." : "Saved, but review flagged: " + r.reasons.join("; "));
    } else if (act === "publish") {
      if (!confirm("Publish this post to " + btn.dataset.platform + "?")) { btn.disabled = false; return; }
      const r = await api(`/api/publish/${id}`, {method: "POST",
        body: JSON.stringify({platform: btn.dataset.platform})});
      toast(r.ok ? "Published: " + (r.post_id || "ok") : "Skipped: " + (r.skipped || r.error));
    }
    await refresh();
  } catch (e) {
    toast("Error: " + e.message);
    btn.disabled = false;
  }
}
async function refresh() {
  STATE = await api("/api/state");
  hideGate();
  render();
}
$("#runBtn").addEventListener("click", async () => {
  const b = $("#runBtn"); b.disabled = true; b.textContent = "Generating...";
  try { await api("/api/run", {method: "POST"}); toast("Drafts generated."); await refresh(); }
  catch (e) { toast("Error: " + e.message); }
  b.disabled = false; b.textContent = "Generate today's drafts";
});
$("#analyzeBtn").addEventListener("click", async () => {
  toast("Pulling metrics...");
  try { await api("/api/analyze", {method: "POST"}); await refresh(); toast("Metrics updated."); }
  catch (e) { toast("Error: " + e.message); }
});
$("#codeBtn").addEventListener("click", async () => {
  CODE = $("#codeInput").value.trim();
  localStorage.setItem("pp_code", CODE);
  try { await refresh(); } catch (e) { /* gate stays */ }
});
refresh().catch(() => {});
