// ═══════════════════════════════════════════════════════════════════
// Arctus.ai dashboard client
// Merged: original live cards + auth/terminal/tier/usage
// ═══════════════════════════════════════════════════════════════════

const $ = (id) => document.getElementById(id);

function ts() {
  return new Date().toLocaleTimeString([], { hour12: false });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;', "'": "&#39;",
  })[c]);
}

async function getJSON(url, opts) {
  const headers = opts?.headers || {};
  // Attach tier header to all API calls.
  const tier = getCurrentTier();
  if (tier) headers["X-Arctus-Tier"] = tier;
  if (!headers["Content-Type"] && opts?.body) headers["Content-Type"] = "application/json";
  const r = await fetch(url, { ...opts, headers });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

// ── 3D Scene Tracking ───────────────────────────────────────────────
const scene = $("scene");
document.addEventListener("mousemove", (e) => {
  const xAxis = (window.innerWidth / 2 - e.pageX) / 50;
  const yAxis = (window.innerHeight / 2 - e.pageY) / 50;
  scene.style.transform = `rotateY(${xAxis}deg) rotateX(${yAxis}deg)`;
});
document.addEventListener("mouseleave", () => {
  scene.style.transform = `rotateY(0deg) rotateX(0deg)`;
});

// ── Authentication ──────────────────────────────────────────────────
function handleLogin() {
  const auth = $("authScreen");
  const dash = $("dashboardScreen");
  auth.style.opacity = "0";
  auth.style.transform = "translateZ(-100px) scale(0.9)";
  setTimeout(() => {
    auth.style.display = "none";
    dash.style.display = "flex";
    setTimeout(() => dash.style.opacity = "1", 50);
    initDashboard();
  }, 400);
}

// ── Theme Toggle ───────────────────────────────────────────────────
function toggleTheme() {
  const body = document.body;
  body.setAttribute("data-theme", body.getAttribute("data-theme") === "dark" ? "sky-light" : "dark");
}

// ── Terminal ────────────────────────────────────────────────────────
function termLog(msg, kind = "info") {
  const terminal = $("terminal");
  const el = document.createElement("div");
  let cls = "";
  if (kind === "system") cls = "system";
  else if (kind === "error") cls = "error";
  else if (kind === "prefix") cls = "prefix";
  el.innerHTML = cls ? `<span class="${cls}">${escapeHtml(msg)}</span>` : escapeHtml(msg);
  terminal.appendChild(el);
  terminal.scrollTop = terminal.scrollHeight;
}

function startNewChat() {
  $("terminal").innerHTML = `<div><span class="system">--- New Session Initiated ---</span></div>`;
  termLog("system:", "prefix");
  termLog("Workspace ready. Awaiting instructions.", "system");
}

function connectMCP() {
  termLog("system:", "prefix");
  termLog("Scanning for local Model Context Protocol servers...", "system");
  refreshMCP();
}

function handleFile(e) {
  if (!e.target.files.length) return;
  termLog("attached:", "prefix");
  termLog(`📎 ${e.target.files[0].name}`);
}

function handlePluginUpload(e) {
  if (!e.target.files.length) return;
  termLog("plugin:", "prefix");
  termLog(`Installing plugin: ${e.target.files[0].name}`);
}

function loadHistory(id) {
  termLog("system:", "prefix");
  termLog(`Restoring session: ${id}`, "system");
}

function handleEnter(e) {
  if (e.key === "Enter" && e.target.value.trim() !== "") {
    const mode = $("agentMode").value;
    const val = e.target.value;
    termLog(`> ${val}`);
    e.target.value = "";

    let modeText = mode === "research" ? "Scraping web and analyzing context..."
                 : mode === "think" ? "Evaluating logical pathways..."
                 : mode === "high" ? "Executing complex pipeline..."
                 : "Processing...";

    // Submit to orchestrate endpoint
    submitTask(val);
  }
}

function scrollToSection(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Subscription Tier ────────────────────────────────────────────────
function getCurrentTier() {
  return localStorage.getItem("arctus_tier") || "free";
}

function setTier(tierName) {
  localStorage.setItem("arctus_tier", tierName);
  // Update profile label
  const labels = { free: "free@arctus", tier1: "tier1@arctus", tier2: "tier2@arctus", tier3: "tier3@arctus", payg: "payg@arctus" };
  $("profileLabel").textContent = (labels[tierName] || "free@arctus") + " ~";

  // Update active-tier highlight
  document.querySelectorAll(".profile-item[data-tier]").forEach(el => {
    el.classList.toggle("active-tier", el.dataset.tier === tierName);
  });

  // Refresh usage for the new tier
  refreshUsage();
  termLog("system:", "prefix");
  termLog(`Tier switched to ${tierName}`, "system");
}

// ── Usage Widget ────────────────────────────────────────────────────
async function refreshUsage() {
  try {
    const d = await getJSON("/api/usage?session_id=web");
    const u = d.usage || {};
    const q = d.quota || {};
    const runs = u.runs || 0;
    const maxRuns = q.monthly_runs || 0;
    const cost = (u.est_cost || 0).toFixed(4);
    const tierLabel = d.tier || "free";

    let text = `Tier: ${tierLabel} | Runs: ${runs}`;
    if (maxRuns !== Infinity && maxRuns !== 0) {
      text += `/${maxRuns}`;
    }
    text += ` | Cost: $${cost}`;

    const widget = $("usageWidget");
    widget.textContent = text;
    const isLimitHit = maxRuns !== Infinity && maxRuns !== 0 && runs >= maxRuns;
    widget.classList.toggle("limit-hit", isLimitHit);
  } catch (e) {
    $("usageWidget").textContent = "Usage: -";
  }
}

// ── Live Cards: Agents ──────────────────────────────────────────────
async function refreshAgents() {
  try {
    const d = await getJSON("/api/agents");
    const s = d.summary || {};
    const lines = Object.entries(s)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}: <b>${v}</b>`);
    $("agent-summary").innerHTML = `Total: <b>${d.total}</b><br>` + lines.join("<br>");
  } catch (e) {
    $("agent-summary").textContent = "Error: " + e.message;
  }
}

// ── Live Cards: MCP ─────────────────────────────────────────────────
async function refreshMCP() {
  try {
    const d = await getJSON("/api/mcp/list");
    const cs = d.connectors || [];
    if (!cs.length) { $("mcp-list").textContent = "None yet."; return; }
    $("mcp-list").innerHTML = cs.map(
      (c) => `${c.name} <span style="color:var(--text-dim)">(${c.transport}, ${c.tools.length} tools)</span>`
    ).join("<br>");
  } catch (e) {
    $("mcp-list").textContent = "Error: " + e.message;
  }
}

function openMCPModal() { $("mcp-modal").classList.remove("hidden"); }
function closeMCPModal() { $("mcp-modal").classList.add("hidden"); }

async function addMCPConnector() {
  const name = $("mcp-name").value.trim();
  const transport = $("mcp-transport").value;
  const url = $("mcp-url").value.trim();
  const command = $("mcp-command").value.trim();
  const apiKey = $("mcp-key").value.trim();
  const tools = $("mcp-tools").value.split(",").map((s) => s.trim()).filter(Boolean);
  if (!name) { alert("Name required"); return; }
  const config = { transport, url, command, api_key: apiKey, tools };
  try {
    await getJSON("/api/mcp/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, config }),
    });
    closeMCPModal();
    termLog(`MCP connector '${name}' connected`);
    refreshMCP();
  } catch (e) {
    alert("Failed: " + e.message);
  }
}

// ── Live Cards: Consortium Peers ─────────────────────────────────────
async function refreshPeers() {
  try {
    const d = await getJSON("/api/consortium/peers");
    const ps = d.peers || [];
    if (!ps.length) { $("peer-list").textContent = "No peers."; return; }
    $("peer-list").innerHTML = ps.map(
      (p) => `${p.name} <span style="color:var(--text-dim)">(${p.base_url})</span>`
    ).join("<br>");
  } catch (e) {
    $("peer-list").textContent = "Error: " + e.message;
  }
}

// ── Orchestrate (terminal → backend) ──────────────────────────────
async function submitTask(promptOverride) {
  const prompt = promptOverride || $("prompt").value.trim();
  if (!prompt) return;
  if (!promptOverride) $("prompt").value = "";

  try {
    const d = await getJSON("/api/orchestrate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, session_id: "web" }),
    });

    if (d.error) {
      // Monthly limit hit?
      if (d.error === "monthly_limit") {
        termLog(`⚠ ${d.detail}`, "error");
      } else {
        termLog(`✗ ${d.error}`, "error");
      }
      refreshUsage();
      return;
    }

    termLog(`complexity=${d.complexity} mode=${d.mode} steps=${(d.steps || []).length} tier=${d.tier || "?"}`);

    for (const w of (d.work || [])) {
      const line = `  [${w.tier}] ${w.step} → ${String(w.result).slice(0, 150)}`;
      termLog(line);
    }
    if (d.verification) {
      termLog(`verify done=${d.verification.done} — ${d.verification.notes}`);
    }
    if (d.usage) {
      const tok = d.usage;
      termLog(`tokens: ${tok.prompt_tokens || 0}in + ${tok.completion_tokens || 0}out`);
    }

    refreshUsage();
  } catch (e) {
    termLog(`✗ ${e.message}`, "error");
  }
}

// ── Refresh All ────────────────────────────────────────────────────
function refreshAll() {
  refreshAgents();
  refreshMCP();
  refreshPeers();
  refreshUsage();
}

// ── Init (called after auth transition) ────────────────────────────
function initDashboard() {
  // Restore tier selection
  const savedTier = getCurrentTier();
  setTier(savedTier);

  // Refresh live cards
  refreshAll();

  termLog("Arctus.ai dashboard ready.", "system");
}

// ── Fallback: if no auth (direct load), show dashboard immediately ───
// This handles the case where the user has already authenticated or
// the page is loaded directly without the auth screen.
(function () {
  // Auto-login if the page was reloaded after auth
  if (sessionStorage.getItem("arctus_authed") === "1") {
    handleLogin();
  }
})();

// Save auth state on login (patch into handleLogin)
const _origHandleLogin = handleLogin;
handleLogin = function () {
  sessionStorage.setItem("arctus_authed", "1");
  _origHandleLogin();
};
