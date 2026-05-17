// dashboard/app.js
// OpenGPA Evaluation Ledger — editorial monograph renderer.
//
// Three sections render from a single index.json:
//   1. KPI strip   — four hero metrics with deltas vs previous round
//   2. Faceted view — per-capability mini-tiles with sparklines
//   3. Timeline grid + narrative cards
//
// No framework. Plain DOM + a tiny set of pure-function aggregators.

(async function main() {
  /* ---------- State ---------- */
  const state = {
    data: null,
    axis: "scenario_type",   // active capability dimension
  };

  /* ---------- Fetch ---------- */
  try {
    const resp = await fetch("index.json", { cache: "no-store" });
    state.data = await resp.json();
  } catch (e) {
    document.querySelector(".paper").innerHTML =
      '<p style="color:#7a2c1f">Failed to load index.json — run scripts/build-eval-dashboard.sh first.</p>';
    return;
  }

  /* ---------- Pre-compute round order + latest ---------- */
  const rounds = [...state.data.rounds].sort((a, b) =>
    (a.date || "").localeCompare(b.date || ""));
  const latest = rounds[rounds.length - 1];
  const prior  = rounds[rounds.length - 2] || null;

  /* ---------- Header ---------- */
  document.getElementById("built-at").textContent =
    formatBuildTimestamp(state.data.built_at);
  document.getElementById("volume-range").textContent =
    rounds.length
      ? `Vol. ${rounds[0].id} → ${latest.id} · ${rounds[0].date} → ${latest.date}`
      : "no data";
  document.getElementById("round-count").textContent =
    `${rounds.length} round${rounds.length === 1 ? "" : "s"} · ${state.data.scenario_types.length} types`;

  /* ---------- Capability nav ---------- */
  const nav = document.getElementById("capability-nav");
  nav.addEventListener("click", e => {
    const btn = e.target.closest("button[data-axis]");
    if (!btn) return;
    nav.querySelectorAll("button").forEach(b => b.classList.toggle("active", b === btn));
    state.axis = btn.dataset.axis;
    renderFacets();
  });

  /* ---------- Render everything ---------- */
  renderKPIs();
  renderFacets();
  renderGrid();
  renderCards();

  /* =================================================================
     KPI STRIP
     ================================================================= */

  function renderKPIs() {
    const co = (r) => r.results.filter(x => x.mode === "code_only");
    const m = computeMetrics(co(latest));
    const mPrior = prior ? computeMetrics(co(prior)) : null;

    setKPI("kpi-solved",
      `${m.solved}<span class="unit">/${m.n}</span>`,
      mPrior ? formatDelta(m.solved - mPrior.solved, "vs " + prior.id, true) : "");
    setKPI("kpi-cost",
      m.tokPerSolve != null
        ? `${(m.tokPerSolve / 1000).toFixed(1)}<span class="unit">k</span>`
        : `<span class="pending">—</span>`,
      mPrior && mPrior.tokPerSolve != null && m.tokPerSolve != null
        ? formatDelta(m.tokPerSolve - mPrior.tokPerSolve, "vs " + prior.id, false)
        : "");
    setKPI("kpi-qualified",
      m.n ? `${Math.round(100 * m.qualified / m.n)}<span class="unit">%</span>` : "—",
      mPrior && mPrior.n
        ? formatDelta(
            Math.round(100 * m.qualified / m.n) - Math.round(100 * mPrior.qualified / mPrior.n),
            "vs " + prior.id, true, "pp")
        : "");
    // GPA lift stays "pending" until any with_gla data shows up.
    const hasGla = latest.results.some(x => x.mode === "with_gla");
    if (hasGla) {
      const gla = computeMetrics(latest.results.filter(x => x.mode === "with_gla"));
      const liftPct = 100 * gla.solved / Math.max(1, gla.n) - 100 * m.solved / Math.max(1, m.n);
      setKPI("kpi-lift",
        `${liftPct >= 0 ? "+" : ""}${liftPct.toFixed(0)}<span class="unit">pp</span>`,
        "GLA − CO @ " + latest.id);
    }
  }

  function setKPI(id, html, delta) {
    const el = document.getElementById(id);
    el.querySelector(".kpi-value").innerHTML = html;
    const deltaEl = el.querySelector(".kpi-delta");
    if (!delta) { deltaEl.textContent = ""; return; }
    deltaEl.innerHTML = delta;
  }

  function formatDelta(diff, label, betterIsHigher, unit = "") {
    if (diff === 0) return `<span>±0${unit} ${label}</span>`;
    const sign = diff > 0 ? "+" : "";
    const cls = ((diff > 0) === betterIsHigher) ? "pos" : "neg";
    const arrow = diff > 0 ? "▲" : "▼";
    const num = unit === "pp"
      ? `${sign}${diff}pp`
      : (Math.abs(diff) > 1000
          ? `${sign}${(diff / 1000).toFixed(1)}k`
          : `${sign}${diff}`);
    return `<span class="${cls}">${arrow} ${num}  ${label}</span>`;
  }

  function formatBuildTimestamp(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      const pad = n => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch (e) { return iso; }
  }

  /* =================================================================
     FACETS  (per-capability mini-tiles + sparklines)
     ================================================================= */

  function renderFacets() {
    const host = document.getElementById("facets");
    host.textContent = "";

    // Collect all bucket values for the active axis (across all rounds)
    const buckets = new Map(); // bucket -> {label, sub, results-by-round}
    for (const round of rounds) {
      for (const r of round.results) {
        if (r.mode !== "code_only") continue;  // baseline only; GLA shows in grid
        const key = String(r[state.axis] ?? "unknown");
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key).push({ round, row: r });
      }
    }

    // Stable display order: framework follows alpha; api/depth/scope/nature
    // each have a canonical order.
    const order = orderForAxis(state.axis);
    const keys = [...buckets.keys()].sort((a, b) => {
      const ai = order.indexOf(a), bi = order.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });

    for (const key of keys) {
      const entries = buckets.get(key);
      // Group entries by round id
      const byRound = new Map();
      for (const { round, row } of entries) {
        if (!byRound.has(round.id)) byRound.set(round.id, []);
        byRound.get(round.id).push(row);
      }
      // Sort round ids by chronological order matching `rounds`
      const orderedRoundIds = rounds.map(r => r.id).filter(rid => byRound.has(rid));
      const series = orderedRoundIds.map(rid => ({
        round_id: rid,
        ...computeMetrics(byRound.get(rid)),
      }));
      host.appendChild(buildFacet(key, series));
    }
  }

  function orderForAxis(axis) {
    switch (axis) {
      case "inferred_api":   return ["webgl", "vulkan", "opengl", "unknown"];
      case "bug_nature":     return ["framework-internal", "consumer-misuse", "user-config", "legacy", "unknown"];
      case "depth_bucket":   return ["shallow", "moderate", "deep"];
      case "fix_scope":      return ["single", "few", "many", "unknown"];
      default: return [];
    }
  }

  function describeBucket(axis, value, series) {
    // Subtitle below the facet name: total scenarios in the bucket
    // observed in the latest round + axis-specific annotation.
    const latestSeries = series[series.length - 1];
    const n = latestSeries ? latestSeries.n : 0;
    const apiTag = {
      "scenario_type": axis === "scenario_type" && value.startsWith("web-")
        ? "webgl"
        : (value.startsWith("native-engine/") ? "vulkan or opengl" : ""),
    }[axis];
    const tag = apiTag ? ` · ${apiTag}` : "";
    return `n = ${n}${tag}`;
  }

  function buildFacet(key, series) {
    const facet = document.createElement("div");
    facet.className = "facet";

    const name = document.createElement("div");
    name.className = "facet-name";
    name.textContent = key;
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = describeBucket(state.axis, key, series);
    name.appendChild(sub);
    facet.appendChild(name);

    const charts = document.createElement("div");
    charts.className = "facet-charts";
    charts.appendChild(buildMini("Solved", series.map(s => ({
      value: s.n ? (s.solved / s.n) : null,
      raw: s.n ? `${s.solved}/${s.n}` : "—",
      pct: true,
      round_id: s.round_id,
    }))));
    charts.appendChild(buildMini("Tokens / Solve", series.map(s => ({
      value: s.tokPerSolve != null ? s.tokPerSolve : null,
      raw: s.tokPerSolve != null ? `${(s.tokPerSolve / 1000).toFixed(1)}k` : "—",
      round_id: s.round_id,
    }))));
    charts.appendChild(buildMini("Qualified", series.map(s => ({
      value: s.n ? (s.qualified / s.n) : null,
      raw: s.n ? `${Math.round(100 * s.qualified / s.n)}%` : "—",
      pct: true,
      round_id: s.round_id,
    }))));
    facet.appendChild(charts);
    return facet;
  }

  function buildMini(label, points) {
    const tile = document.createElement("div");
    tile.className = "mini";
    const lab = document.createElement("div");
    lab.className = "mini-label";
    lab.textContent = label;
    tile.appendChild(lab);

    const latestPoint = points[points.length - 1] || {};
    const val = document.createElement("div");
    val.className = "mini-value";
    val.innerHTML = latestPoint.raw && latestPoint.raw !== "—"
      ? latestPoint.raw
      : '<span class="mini-value empty">—</span>';
    tile.appendChild(val);

    // Sparkline: bar per round, height ~ normalized value.
    const validValues = points.map(p => p.value).filter(v => v != null && !Number.isNaN(v));
    const maxV = validValues.length ? Math.max(...validValues) : 1;
    const spark = document.createElement("div");
    spark.className = "mini-spark";
    points.forEach((p, i) => {
      const bar = document.createElement("div");
      const isLatest = i === points.length - 1;
      if (p.value == null || Number.isNaN(p.value)) {
        bar.className = "bar empty";
      } else {
        bar.className = isLatest ? "bar latest" : "bar";
        const h = maxV > 0 ? Math.max(4, Math.round((p.value / maxV) * 32)) : 1;
        bar.style.height = `${h}px`;
      }
      bar.title = `${p.round_id}: ${p.raw}`;
      spark.appendChild(bar);
    });
    tile.appendChild(spark);

    // Axis stamp: first/last round id under the sparkline
    if (points.length > 1) {
      const axis = document.createElement("div");
      axis.className = "mini-axis";
      const first = document.createElement("span");
      first.textContent = points[0].round_id;
      const last = document.createElement("span");
      last.textContent = points[points.length - 1].round_id;
      axis.appendChild(first);
      axis.appendChild(last);
      tile.appendChild(axis);
    }
    return tile;
  }

  /* =================================================================
     AGGREGATORS
     ================================================================= */

  function computeMetrics(rows) {
    const n = rows.length;
    let solved = 0, qualified = 0, totalTokens = 0;
    for (const r of rows) {
      if (r.solved) {
        solved += 1;
        totalTokens += r.output_tokens || 0;
      }
      if (r.qualified) qualified += 1;
    }
    return {
      n,
      solved,
      qualified,
      tokPerSolve: solved > 0 ? totalTokens / solved : null,
    };
  }

  /* =================================================================
     SCENARIO TIMELINE GRID
     ================================================================= */

  function renderGrid() {
    const container = document.getElementById("grid-container");
    container.textContent = "";
    const table = document.createElement("table");
    table.className = "timeline";

    // Group: scenario_id -> { latest scenario_type, rows by `${round}|${mode}` }
    const byScenario = new Map();
    for (const round of rounds) {
      for (const r of round.results) {
        let s = byScenario.get(r.scenario_id);
        if (!s) {
          s = { type: r.scenario_type, byRound: {}, isStable: false };
          byScenario.set(r.scenario_id, s);
        }
        s.type = r.scenario_type;
        if (r.expected_failure) s.isStable = true;
        s.byRound[`${round.id}|${r.mode}`] = r;
      }
    }

    // Header: scenario col + each round × {CO, GLA}
    const thead = document.createElement("thead");
    const trHead = document.createElement("tr");
    trHead.appendChild(elem("th", "scenario"));
    const colKeys = []; // {round_id, mode}
    for (const round of rounds) {
      for (const mode of ["code_only", "with_gla"]) {
        colKeys.push({ round_id: round.id, mode });
        const th = elem("th", `${round.id}·${mode === "code_only" ? "CO" : "GLA"}`);
        if (mode === "with_gla") th.classList.add("col-gla");
        trHead.appendChild(th);
      }
    }
    thead.appendChild(trHead);
    table.appendChild(thead);

    // Body — grouped by latest scenario_type
    const byType = new Map();
    for (const [sid, s] of byScenario.entries()) {
      if (!byType.has(s.type)) byType.set(s.type, []);
      byType.get(s.type).push({ sid, ...s });
    }
    const tbody = document.createElement("tbody");
    for (const [type, sceneList] of [...byType.entries()].sort()) {
      const trGroup = document.createElement("tr");
      trGroup.className = "type-header";
      const tdGroup = elem("td", type);
      tdGroup.colSpan = colKeys.length + 1;
      trGroup.appendChild(tdGroup);
      tbody.appendChild(trGroup);

      for (const s of sceneList.sort((a, b) => a.sid.localeCompare(b.sid))) {
        const tr = document.createElement("tr");
        if (s.isStable) tr.classList.add("stable");
        const sidCell = elem("td", shortenSid(s.sid));
        sidCell.className = "scenario-cell";
        sidCell.title = s.sid;
        tr.appendChild(sidCell);
        for (const col of colKeys) {
          const cell = document.createElement("td");
          cell.className = "cell";
          if (col.mode === "with_gla") cell.classList.add("col-gla");
          const r = s.byRound[`${col.round_id}|${col.mode}`];
          if (!r) {
            cell.textContent = "—";
            cell.classList.add("cell-absent");
          } else if (r.qualified) {
            cell.textContent = "●";
            cell.classList.add("cell-qualified");
            attachTooltip(cell, r);
          } else if (r.solved) {
            cell.textContent = "◐";
            cell.classList.add("cell-rescued");
            attachTooltip(cell, r);
          } else {
            cell.textContent = "○";
            cell.classList.add("cell-failed");
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
    // Drop the mining-prefix (rfc2ac5 / r5211bd) and keep the descriptive tail.
    const parts = sid.split("_");
    if (parts.length <= 4) return sid;
    const tail = parts.slice(-4).join(" "); // descriptive end words
    return tail;
  }

  function attachTooltip(el, r) {
    el.addEventListener("mouseenter", e => {
      const tt = document.getElementById("tooltip");
      tt.textContent = "";
      const b = document.createElement("b");
      b.textContent = r.scenario_id;
      tt.appendChild(b);
      tt.appendChild(document.createElement("br"));
      tt.appendChild(document.createTextNode(
        `${r.mode} · ${r.tier} · ${r.scorer}/${r.confidence}`));
      tt.appendChild(document.createElement("br"));
      tt.appendChild(document.createTextNode(
        `tok=${r.output_tokens}  tools=${r.tool_calls}  qualified=${r.qualified ? "yes" : "no"}`));
      tt.appendChild(document.createElement("br"));
      tt.appendChild(document.createTextNode(
        `${r.inferred_api} · ${r.bug_nature} · fix:${r.fix_scope}(${r.fix_files_count}) · ${r.depth_bucket}`));
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

  /* =================================================================
     ROUND NARRATIVE CARDS
     ================================================================= */

  function renderCards() {
    const container = document.getElementById("card-container");
    container.textContent = "";
    const ordered = [...rounds].reverse();   // newest first
    ordered.forEach((round, i) => {
      const card = document.createElement("div");
      card.className = "card" + (i === 0 ? " expanded" : "");

      const header = document.createElement("div");
      header.className = "card-header";
      const idDiv = elem("div", round.id);
      idDiv.className = "id";
      const dateDiv = elem("div", round.date || "");
      dateDiv.className = "date";
      const headlineDiv = elem("div", round.headline || round.id);
      headlineDiv.className = "headline";
      const toggle = elem("div", "▾");
      toggle.className = "toggle";
      header.append(idDiv, dateDiv, headlineDiv, toggle);
      header.addEventListener("click", () => card.classList.toggle("expanded"));

      const body = document.createElement("div");
      body.className = "card-body";
      if (round.narrative_md) {
        body.innerHTML = marked.parse(round.narrative_md);
      } else {
        const p = elem("p", "(no round log)");
        body.appendChild(p);
      }
      card.appendChild(header);
      card.appendChild(body);
      container.appendChild(card);
    });
  }
})();
