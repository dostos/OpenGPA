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

  /* ===== Scenario × round grid ===== */

  function renderGrid() {
    const container = document.getElementById("grid-container");
    container.innerHTML = "";
    const table = document.createElement("table");
    table.className = "timeline";

    // Group scenarios by latest scenario_type
    const byScenario = new Map(); // sid -> { type, byRound: { round_id|mode: row } }
    for (const round of state.data.rounds) {
      for (const r of round.results) {
        if (state.tier !== "all" && r.tier !== state.tier) continue;
        let s = byScenario.get(r.scenario_id);
        if (!s) {
          s = { type: r.scenario_type, byRound: {}, isStable: false };
          byScenario.set(r.scenario_id, s);
        }
        // Latest seen wins for type
        s.type = r.scenario_type;
        if (r.expected_failure) s.isStable = true;
        const key = `${round.id}|${r.mode}`;
        s.byRound[key] = r;
      }
    }

    // Header: scenario column + one column per (round, mode) that has data
    const thead = document.createElement("thead");
    const trMode = document.createElement("tr");
    trMode.appendChild(elem("th", "scenario"));
    const roundColumns = []; // [{round_id, mode}]
    for (const round of state.data.rounds) {
      for (const mode of ["code_only", "with_gla"]) {
        const anyRow = round.results.some(r =>
          r.mode === mode && (state.tier === "all" || r.tier === state.tier)
        );
        if (!anyRow) continue;
        roundColumns.push({ round_id: round.id, mode });
        trMode.appendChild(elem("th", `${round.id} · ${mode === "code_only" ? "CO" : "GLA"}`));
      }
    }
    thead.appendChild(trMode);
    table.appendChild(thead);

    // Body, grouped by type
    const tbody = document.createElement("tbody");
    const byType = new Map();
    for (const [sid, s] of byScenario.entries()) {
      if (!byType.has(s.type)) byType.set(s.type, []);
      byType.get(s.type).push({ sid, ...s });
    }
    for (const [type, scenarios] of [...byType.entries()].sort()) {
      const tr = document.createElement("tr");
      tr.className = "type-header";
      const td = elem("td", type);
      td.colSpan = roundColumns.length + 1;
      tr.appendChild(td);
      tbody.appendChild(tr);
      for (const s of scenarios.sort((a, b) => a.sid.localeCompare(b.sid))) {
        const tr = document.createElement("tr");
        if (s.isStable) tr.className = "stable";
        const sidCell = elem("td", shortenSid(s.sid));
        sidCell.style.textAlign = "left";
        sidCell.title = s.sid;
        tr.appendChild(sidCell);
        for (const col of roundColumns) {
          const cell = document.createElement("td");
          cell.className = "cell";
          const r = s.byRound[`${col.round_id}|${col.mode}`];
          if (!r) {
            cell.textContent = "";
            cell.classList.add("cell-skipped");
          } else if (r.solved && r.scorer === "file_level" && r.confidence === "high") {
            cell.textContent = "✓";
            cell.classList.add("cell-hi");
            attachTooltip(cell, r);
          } else if (r.solved) {
            cell.textContent = "✓";
            cell.classList.add("cell-mid");
            attachTooltip(cell, r);
          } else {
            cell.textContent = "✗";
            cell.classList.add("cell-lo");
            attachTooltip(cell, r);
          }
          tr.appendChild(cell);
        }
        tbody.appendChild(tr);
      }
    }
    table.appendChild(tbody);
    container.appendChild(table);
  }

  function shortenSid(sid) {
    const parts = sid.split("_");
    return parts.slice(-3).join("_");
  }

  function attachTooltip(el, r) {
    el.addEventListener("mouseenter", e => {
      const tt = document.getElementById("tooltip");
      // Build via DOM nodes; scenario_id / expected_failure.reason are
      // dev-authored but textContent removes the HTML-injection footgun.
      tt.textContent = "";
      const b = document.createElement("b");
      b.textContent = r.scenario_id;
      tt.appendChild(b);
      tt.appendChild(document.createElement("br"));
      tt.appendChild(document.createTextNode(`mode=${r.mode} tier=${r.tier}`));
      tt.appendChild(document.createElement("br"));
      tt.appendChild(document.createTextNode(`verdict=${r.scorer}/${r.confidence}`));
      tt.appendChild(document.createElement("br"));
      tt.appendChild(document.createTextNode(`tok=${r.output_tokens} tools=${r.tool_calls}`));
      if (r.expected_failure) {
        tt.appendChild(document.createElement("br"));
        tt.appendChild(document.createTextNode(`⊘ ${r.expected_failure.reason || ""}`));
      }
      tt.hidden = false;
      tt.style.left = (e.pageX + 12) + "px";
      tt.style.top = (e.pageY + 12) + "px";
    });
    el.addEventListener("mouseleave", () => {
      document.getElementById("tooltip").hidden = true;
    });
  }

  function elem(tag, text) {
    const e = document.createElement(tag);
    e.textContent = text;
    return e;
  }

  /* ===== Per-round narrative cards ===== */

  function renderCards() {
    const container = document.getElementById("card-container");
    container.innerHTML = "";
    // Reverse: newest round first
    const ordered = [...state.data.rounds].reverse();
    for (let i = 0; i < ordered.length; i++) {
      const round = ordered[i];
      const card = document.createElement("div");
      card.className = "card";
      const header = document.createElement("div");
      header.className = "card-header";
      // Use textContent for the dynamic fields (id, date, headline come
      // from developer-authored data but textContent costs nothing and
      // removes a class of footgun if a headline ever contains "<" or "&").
      const idSpan = elem("span", round.id);
      idSpan.className = "id";
      const dateSpan = elem("span", round.date || "");
      dateSpan.className = "date";
      const headlineSpan = elem("span", round.headline);
      headlineSpan.className = "headline";
      const toggleSpan = elem("span", "▼");
      toggleSpan.className = "toggle";
      header.append(idSpan, dateSpan, headlineSpan, toggleSpan);
      const body = document.createElement("div");
      body.className = "card-body";
      if (round.narrative_md) {
        // marked output is HTML by design — the narrative IS the round log.
        body.innerHTML = marked.parse(round.narrative_md);
      } else {
        const empty = elem("p", "(no round log)");
        body.appendChild(empty);
      }
      if (i === 0) body.classList.add("expanded");
      header.addEventListener("click", () => body.classList.toggle("expanded"));
      card.appendChild(header);
      card.appendChild(body);
      container.appendChild(card);
    }
  }
})();
