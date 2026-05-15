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

  /* ===== Per-type panels (Plotly) ===== */

  function renderPanels() {
    const types = state.data.scenario_types.filter(t => t !== "unknown");
    const grid = document.getElementById("panel-grid");
    grid.innerHTML = "";
    for (const type of types) {
      const panel = document.createElement("div");
      panel.className = "panel";
      const title = document.createElement("div");
      title.className = "panel-title";
      title.textContent = `${type} — ${state.metric === "solve_pct" ? "solve %" : "output tokens / solved"}`;
      panel.appendChild(title);
      const chartDiv = document.createElement("div");
      panel.appendChild(chartDiv);
      grid.appendChild(panel);

      const traces = buildTraces(type);
      const layout = {
        height: 260,
        margin: { l: 40, r: 12, t: 8, b: 32 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: "#e2e8f0", size: 11 },
        xaxis: { color: "#94a3b8", gridcolor: "#334155" },
        yaxis: {
          color: "#94a3b8",
          gridcolor: "#334155",
          rangemode: "tozero",
          ticksuffix: state.metric === "solve_pct" ? "%" : "",
        },
        legend: { font: { size: 10 }, orientation: "h", y: -0.25 },
      };
      Plotly.newPlot(chartDiv, traces, layout, {
        displayModeBar: false,
        responsive: true,
      });
    }
  }

  function buildTraces(type) {
    const modes = ["code_only", "with_gla"];
    const tiers = state.tier === "all"
      ? ["haiku", "sonnet", "opus"]
      : [state.tier];
    const traces = [];
    for (const mode of modes) {
      for (const tier of tiers) {
        const pts = perRoundMetric(type, mode, tier);
        if (pts.x.length === 0) continue;
        traces.push({
          x: pts.x,
          y: pts.y,
          mode: "lines+markers",
          name: `${mode === "code_only" ? "CO" : "GLA"} · ${tier}`,
          line: {
            color: mode === "code_only" ? "#60a5fa" : "#fb923c",
            dash: tier === "haiku" ? "solid" : (tier === "sonnet" ? "dash" : "dot"),
            width: 2,
          },
          marker: { size: 6 },
          hovertemplate:
            `<b>%{x}</b><br>${mode} · ${tier}<br>` +
            (state.metric === "solve_pct" ? "solve: %{y:.0f}%" : "tok/✓: %{y:.0f}") +
            " (n=%{customdata})<extra></extra>",
          customdata: pts.n,
          connectgaps: false,
        });
      }
    }
    return traces;
  }

  function perRoundMetric(type, mode, tier) {
    const x = [], y = [], n = [];
    for (const round of state.data.rounds) {
      const rows = round.results.filter(r =>
        r.scenario_type === type && r.mode === mode && r.tier === tier
        && (state.includeStable || !r.expected_failure)
      );
      if (rows.length === 0) continue;
      x.push(round.id);
      n.push(rows.length);
      if (state.metric === "solve_pct") {
        const solved = rows.filter(r => r.solved).length;
        y.push((solved / rows.length) * 100);
      } else {
        const solvedRows = rows.filter(r => r.solved);
        if (solvedRows.length === 0) { y.push(null); continue; }
        const total = solvedRows.reduce((s, r) => s + r.output_tokens, 0);
        y.push(total / solvedRows.length);
      }
    }
    return { x, y, n };
  }

  // Stubs for substep 1c
  function renderGrid() {}
  function renderCards() {}
})();
