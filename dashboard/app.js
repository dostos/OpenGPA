// dashboard/app.js
(async function main() {
  const state = {
    data: null,
    metric: "solve_pct",
    tier: "all",
    includeStable: false,
  };

  try {
    const resp = await fetch("index.json", { cache: "no-store" });
    state.data = await resp.json();
  } catch (e) {
    document.querySelector("main").innerHTML =
      `<p style="color:#fca5a5">Failed to load index.json — run scripts/build-eval-dashboard.sh first.</p>`;
    return;
  }

  document.getElementById("built-at").textContent =
    "built " + state.data.built_at;

  const metricSel = document.getElementById("metric-select");
  const tierSel = document.getElementById("tier-select");
  const stableChk = document.getElementById("include-stable");
  metricSel.addEventListener("change", e => { state.metric = e.target.value; renderAll(); });
  tierSel.addEventListener("change", e => { state.tier = e.target.value; renderAll(); });
  stableChk.addEventListener("change", e => { state.includeStable = e.target.checked; renderAll(); });

  renderAll();

  function renderAll() {
    renderPanels();
    renderGrid();
    renderCards();
  }

  // Stub renderers — filled in by substeps 1b and 1c.
  function renderPanels() {}
  function renderGrid() {}
  function renderCards() {}
})();
