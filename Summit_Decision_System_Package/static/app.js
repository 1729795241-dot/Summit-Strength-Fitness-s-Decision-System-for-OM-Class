const state = {
  current: null,
};

const el = (id) => document.getElementById(id);

function money(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return value || "";
  return `$${Math.round(n).toLocaleString()}`;
}

function setStatus(text, mode = "ready") {
  const badge = el("statusBadge");
  badge.textContent = text;
  const colors = {
    ready: "#2e74b5",
    running: "#b97213",
    done: "#2f7d46",
    error: "#b83232",
  };
  badge.style.background = colors[mode] || colors.ready;
}

function showMessage(text, isError = false) {
  const box = el("message");
  if (!text) {
    box.hidden = true;
    box.textContent = "";
    box.className = "message";
    return;
  }
  box.hidden = false;
  box.textContent = text;
  box.className = isError ? "message error" : "message";
}

function riskClass(level) {
  const normalized = String(level || "").toLowerCase();
  if (normalized.includes("high")) return "risk-high";
  if (normalized.includes("medium")) return "risk-medium";
  if (normalized.includes("low")) return "risk-low";
  return "";
}

function renderDecisions(aiReview) {
  const decision = el("executiveDecision");
  const list = el("decisionList");
  const recommendations = aiReview?.recommendations || [];
  decision.textContent = aiReview?.executive_decision || "No review loaded.";
  list.innerHTML = "";

  recommendations.forEach((item) => {
    const card = document.createElement("article");
    card.className = "decision-card";
    card.innerHTML = `
      <div class="decision-head">
        <strong>${item.decision_area || "Decision"}</strong>
        <span class="pill ${riskClass(item.risk_level)}">${item.risk_level || "Risk"}</span>
      </div>
      <p><strong>${item.approval_status || "Status"}.</strong> ${item.recommendation || ""}</p>
      <p>${item.rationale || ""}</p>
      <p>${item.managerial_check || ""}</p>
    `;
    list.appendChild(card);
  });
}

function renderKpis(rows) {
  const stack = el("kpiCards");
  stack.innerHTML = "";
  (rows || []).forEach((row) => {
    const card = document.createElement("div");
    card.className = "metric";
    card.innerHTML = `
      <strong>${row.scenario || "Scenario"}</strong>
      <span>Service gap: ${row.service_gap_units || ""} units</span>
      <span>Penalty: ${money(row.expected_service_gap_penalty)}</span>
      <span>Transfer cost: ${money(row.transfer_cost)}</span>
      <span>Net penalty: ${money(row.net_penalty_after_transfer_cost)}</span>
    `;
    stack.appendChild(card);
  });
}

function renderTransfers(rows) {
  const body = el("transferRows");
  body.innerHTML = "";
  (rows || []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.from_region || ""} → ${row.to_region || ""}</td>
      <td>${row.sku || ""}</td>
      <td>${row.quantity_units || ""}</td>
      <td>${money(row.net_benefit_before_handling_risk)}</td>
    `;
    body.appendChild(tr);
  });
}

function renderProduction(rows) {
  const body = el("productionRows");
  body.innerHTML = "";
  (rows || []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.sku || ""}</td>
      <td>${row.network_surplus_units || ""}</td>
      <td>${row.recommended_production_adjustment_pct || "0"}%</td>
    `;
    body.appendChild(tr);
  });
}

function render(data) {
  const payload = data?.data || data;
  state.current = payload;
  renderDecisions(payload?.ai_review || {});
  renderKpis(payload?.kpis || []);
  renderTransfers(payload?.transfers || []);
  renderProduction(payload?.production || []);
}

async function fetchCurrent() {
  const res = await fetch("/api/current");
  const data = await res.json();
  render(data);
  setStatus(data.ok ? "Loaded" : "Ready", data.ok ? "done" : "ready");
}

async function runSystem() {
  const apiKey = el("apiKey").value.trim();
  if (!apiKey) {
    showMessage("Enter a DeepSeek key to run a fresh review.", true);
    setStatus("Needs key", "error");
    return;
  }

  setStatus("Running", "running");
  showMessage("Running the inventory model and asking DeepSeek to review the result...");
  el("runBtn").disabled = true;
  el("refreshBtn").disabled = true;
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        apiKey,
        model: el("model").value.trim(),
        baseUrl: el("baseUrl").value.trim(),
      }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Run failed");
    render(data.data);
    showMessage("Review complete. Output files have been refreshed.");
    setStatus("Done", "done");
  } catch (err) {
    showMessage(err.message, true);
    setStatus("Error", "error");
  } finally {
    el("runBtn").disabled = false;
    el("refreshBtn").disabled = false;
  }
}

el("runBtn").addEventListener("click", runSystem);
el("refreshBtn").addEventListener("click", fetchCurrent);
fetchCurrent().catch((err) => {
  showMessage(err.message, true);
  setStatus("Error", "error");
});
