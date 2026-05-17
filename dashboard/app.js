// dashboard/app.js
// OpenGPA Evaluation Ledger — comparison renderer.
//
// SPINE: code_only vs with_gla, per capability bucket. The dashboard
// answers the project's foundational question — "does GPA help the
// agent solve graphics bugs?" — by pairing every (round, scenario)
// that ran in both modes and aggregating CO vs GLA side-by-side.
//
// Round-over-round trends are NOT the headline. Aggregating across
// rounds (instead of charting per-round trajectories) lets the
// dashboard show the comparison directly. Per-scenario history still
// lives in the timeline grid further down.

(async function main() {
  const state = {
    data: null,
    axis: "scenario_type",
  };

  try {
    const resp = await fetch("index.json", { cache: "no-store" });
    state.data = await resp.json();
  } catch (e) {
    document.querySelector(".paper").innerHTML =
      '<p style="color:#7a2c1f">Failed to load index.json — run scripts/build-eval-dashboard.sh first.</p>';
    return;
  }

  const rounds = [...state.data.rounds].sort((a, b) =>
    (a.date || "").localeCompare(b.date || ""));

  /* ---------- Pair CO/GLA rows within each round ---------- */
  // A "pair" is one (round, scenario) where BOTH modes ran. That's
  // the unit of CO-vs-GLA comparison; rows with only one mode
  // contribute to the CO-only or GLA-only buckets but not to lift.
  const allRows = [];           // every result row, flattened
  const pairs = [];             // { round_id, scenario_id, CO, GLA }
  const pairedRoundIds = new Set();
  for (const round of rounds) {
    const byScenario = new Map();
    for (const r of round.results) {
      allRows.push({ ...r, round_id: round.id });
      if (!byScenario.has(r.scenario_id)) byScenario.set(r.scenario_id, {});
      byScenario.get(r.scenario_id)[r.mode] = r;
    }
    for (const [sid, modes] of byScenario.entries()) {
      if (modes.code_only && modes.with_gla) {
        pairs.push({
          round_id: round.id,
          scenario_id: sid,
          scenario_type: modes.code_only.scenario_type,
          inferred_api: modes.code_only.inferred_api,
          bug_nature: modes.code_only.bug_nature,
          depth_bucket: modes.code_only.depth_bucket,
          fix_scope: modes.code_only.fix_scope,
          expected_failure: modes.code_only.expected_failure,
          CO: modes.code_only,
          GLA: modes.with_gla,
        });
        pairedRoundIds.add(round.id);
      }
    }
  }

  /* ---------- Header ---------- */
  document.getElementById("built-at").textContent = formatBuildTimestamp(state.data.built_at);
  const subtitle = document.getElementById("volume-range");
  const pairedList = [...pairedRoundIds].sort();
  const coOnlyRounds = rounds.filter(r => !pairedRoundIds.has(r.id)).map(r => r.id);
  subtitle.innerHTML = pairedList.length
    ? `paired rounds <em>${pairedList[0]} → ${pairedList[pairedList.length - 1]}</em>`
      + (coOnlyRounds.length ? ` · code-only only: <em>${coOnlyRounds.join(", ")}</em>` : "")
    : "no paired data";
  document.getElementById("round-count").textContent =
    `${pairs.length} CO×GLA pairs across ${pairedList.length} rounds`;

  /* ---------- Capability nav ---------- */
  const nav = document.getElementById("capability-nav");
  nav.addEventListener("click", e => {
    const btn = e.target.closest("button[data-axis]");
    if (!btn) return;
    nav.querySelectorAll("button").forEach(b => b.classList.toggle("active", b === btn));
    state.axis = btn.dataset.axis;
    renderFacets();
  });

  /* ---------- Render ---------- */
  renderCorpus();
  renderKPIs();
  renderFacets();
  renderGrid();
  renderCards();

  /* =================================================================
     CORPUS — dataset overview (independent of eval results)
     ================================================================= */

  function renderCorpus() {
    const c = state.data.corpus || { total: 0 };
    const host = document.getElementById("corpus-grid");
    if (!host) return;
    host.textContent = "";
    if (!c.total) {
      const empty = document.createElement("div");
      empty.className = "corpus-empty";
      empty.textContent = "(corpus stats unavailable — tests/eval/ not present in this checkout)";
      host.appendChild(empty);
      return;
    }
    // Headline tile: total + headline annotations
    const headline = document.createElement("div");
    headline.className = "corpus-headline";
    const num = document.createElement("div");
    num.className = "corpus-headline-value";
    num.textContent = c.total;
    headline.appendChild(num);
    const lab = document.createElement("div");
    lab.className = "corpus-headline-label";
    lab.innerHTML =
      `scenarios total<br>` +
      `<span>${c.with_fix_metadata || 0} fix-annotated · ` +
      `${c.with_upstream_snapshot || 0} with snapshot · ` +
      `${c.with_expected_failure || 0} stable-failure</span>`;
    headline.appendChild(lab);
    host.appendChild(headline);

    // Distribution tiles — each is a sparkbar list
    host.appendChild(distTile("By category", c.by_category, "category"));
    host.appendChild(distTile("By framework", c.by_framework, "framework"));
    host.appendChild(distTile("By backend api", c.by_backend_api, "api"));
    host.appendChild(distTile("By bug class (fix)", c.by_md_bug_class, "bug-class"));
    host.appendChild(distTile("By source type", c.by_source_type, "source"));
    host.appendChild(distTile("By status", c.by_status, "status"));
    host.appendChild(distTile("Fix scope", c.fix_scope_distribution, "scope"));
  }

  function distTile(label, counter, kind) {
    const tile = document.createElement("div");
    tile.className = "corpus-tile";
    const head = document.createElement("div");
    head.className = "corpus-tile-label";
    head.textContent = label;
    tile.appendChild(head);
    const rows = document.createElement("div");
    rows.className = "corpus-rows";
    if (!counter) {
      tile.appendChild(rows);
      return tile;
    }
    const entries = Object.entries(counter);
    const max = entries.reduce((m, [, v]) => Math.max(m, v), 1);
    for (const [key, val] of entries) {
      const row = document.createElement("div");
      row.className = "corpus-row";
      const k = document.createElement("span");
      k.className = "corpus-key";
      k.textContent = key;
      const bar = document.createElement("span");
      bar.className = "corpus-bar";
      const fill = document.createElement("span");
      fill.className = `corpus-fill kind-${kind}`;
      fill.style.width = `${(val / max) * 100}%`;
      bar.appendChild(fill);
      const n = document.createElement("span");
      n.className = "corpus-n";
      n.textContent = val;
      row.append(k, bar, n);
      rows.appendChild(row);
    }
    tile.appendChild(rows);
    return tile;
  }

  /* =================================================================
     KPI STRIP — paired CO vs GLA aggregate
     ================================================================= */

  function renderKPIs() {
    const m = aggregate(pairs);
    renderPairedKPI("kpi-solved",
      m.n ? `${m.coSolved}/${m.n}` : "—",
      m.n ? `${m.glaSolved}/${m.n}` : "—",
      m.n ? formatLift(m.glaSolved - m.coSolved, m.n, "pp") : "");
    renderPairedKPI("kpi-cost",
      m.coTokPerSolve != null ? `${(m.coTokPerSolve / 1000).toFixed(1)}k` : "—",
      m.glaTokPerSolve != null ? `${(m.glaTokPerSolve / 1000).toFixed(1)}k` : "—",
      (m.coTokPerSolve && m.glaTokPerSolve)
        ? `ratio ${(m.glaTokPerSolve / m.coTokPerSolve).toFixed(2)}×`
        : "");
    renderPairedKPI("kpi-qualified",
      m.n ? `${Math.round(100 * m.coQualified / m.n)}%` : "—",
      m.n ? `${Math.round(100 * m.glaQualified / m.n)}%` : "—",
      m.n
        ? formatLift(m.glaQualified - m.coQualified, m.n, "pp")
        : "");
    // Final tile: scope footprint — how much of the data is paired
    const totalPairsPotential = allRows.filter(r => r.mode === "code_only").length;
    renderPairedKPI("kpi-coverage",
      `${pairs.length}/${totalPairsPotential}`,
      coOnlyRounds.length ? `+${coOnlyRounds.length} co-only` : "—",
      `${Math.round(100 * pairs.length / Math.max(1, totalPairsPotential))}% paired`);
  }

  function renderPairedKPI(id, coValue, glaValue, footnote) {
    const el = document.getElementById(id);
    if (!el) return;
    const slots = el.querySelectorAll(".kpi-pair-value");
    if (slots[0]) slots[0].textContent = coValue;
    if (slots[1]) slots[1].textContent = glaValue;
    const fn = el.querySelector(".kpi-note");
    if (fn) fn.innerHTML = footnote || "";
  }

  function formatLift(diff, n, unit = "") {
    if (n === 0) return "—";
    const pct = (diff / n) * 100;
    const sign = pct >= 0 ? "+" : "";
    const cls = diff >= 0 ? "pos" : "neg";
    const arrow = diff > 0 ? "▲" : (diff < 0 ? "▼" : "·");
    return `lift <span class="${cls}">${arrow} ${sign}${pct.toFixed(0)}${unit}</span>`;
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
     FACETS — per-bucket CO vs GLA paired comparison
     ================================================================= */

  function renderFacets() {
    const host = document.getElementById("facets");
    host.textContent = "";

    // Buckets from PAIRED data only — the comparison view excludes
    // CO-only rounds. Buckets that only exist in CO-only data are
    // surfaced in an "unpaired" note below.
    const buckets = new Map(); // bucket -> [pair, pair, ...]
    for (const p of pairs) {
      const key = String(p[state.axis] ?? "unknown");
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(p);
    }

    const order = orderForAxis(state.axis);
    const keys = [...buckets.keys()].sort((a, b) => {
      const ai = order.indexOf(a), bi = order.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });

    if (keys.length === 0) {
      const empty = document.createElement("div");
      empty.className = "facet-empty";
      empty.innerHTML =
        '<em>No paired CO×GLA data for the active axis.</em><br>' +
        'R16+ rounds dropped <code>with_gla</code> on source-less ' +
        'scenarios; only r12c–r15 currently produce paired rows.';
      host.appendChild(empty);
      return;
    }

    for (const key of keys) {
      host.appendChild(buildFacet(key, buckets.get(key)));
    }

    // CO-only addendum (scenarios that only ever ran without GLA)
    const coOnlyBuckets = new Map();
    for (const r of allRows) {
      if (r.mode !== "code_only") continue;
      if (pairs.some(p => p.round_id === r.round_id && p.scenario_id === r.scenario_id)) continue;
      const key = String(r[state.axis] ?? "unknown");
      if (!coOnlyBuckets.has(key)) coOnlyBuckets.set(key, []);
      coOnlyBuckets.get(key).push(r);
    }
    if (coOnlyBuckets.size > 0) {
      const note = document.createElement("div");
      note.className = "facet-empty";
      note.innerHTML =
        `<em>Code-only without paired GLA:</em> ` +
        [...coOnlyBuckets.entries()]
          .map(([k, v]) => `${k} (${v.length})`)
          .join(" · ") +
        '. These rows are visible in the timeline grid below but cannot contribute to lift.';
      host.appendChild(note);
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

  function buildFacet(key, bucketPairs) {
    const m = aggregate(bucketPairs);
    const facet = document.createElement("div");
    facet.className = "facet";

    const name = document.createElement("div");
    name.className = "facet-name";
    name.textContent = key;
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = `${m.n} pair${m.n === 1 ? "" : "s"}`;
    name.appendChild(sub);
    facet.appendChild(name);

    const grid = document.createElement("div");
    grid.className = "facet-pair";

    grid.appendChild(buildMetricRow("Solved",
      m.coSolved, m.glaSolved, m.n,
      v => `${v}/${m.n}`,
      m.glaSolved - m.coSolved,
      "pp", m.n));
    grid.appendChild(buildMetricRow("Tokens / Solve",
      m.coTokPerSolve != null ? Math.round(m.coTokPerSolve) : null,
      m.glaTokPerSolve != null ? Math.round(m.glaTokPerSolve) : null,
      null,
      v => v == null ? "—" : `${(v / 1000).toFixed(1)}k`,
      null, "", null,
      (m.coTokPerSolve && m.glaTokPerSolve)
        ? `${(m.glaTokPerSolve / m.coTokPerSolve).toFixed(2)}× ratio`
        : null));
    grid.appendChild(buildMetricRow("Qualified",
      m.coQualified, m.glaQualified, m.n,
      v => `${Math.round(100 * v / Math.max(1, m.n))}%`,
      m.glaQualified - m.coQualified,
      "pp", m.n));

    facet.appendChild(grid);
    return facet;
  }

  function buildMetricRow(label, coVal, glaVal, denom, fmt, diff, unit, total, ratioStr) {
    const row = document.createElement("div");
    row.className = "metric-row";

    const lab = document.createElement("div");
    lab.className = "metric-label";
    lab.textContent = label;
    row.appendChild(lab);

    const co = document.createElement("div");
    co.className = "metric-cell co";
    co.innerHTML = `<span class="metric-mode">CO</span><span class="metric-value">${fmt(coVal)}</span>`;
    row.appendChild(co);

    const gla = document.createElement("div");
    gla.className = "metric-cell gla";
    gla.innerHTML = `<span class="metric-mode">GLA</span><span class="metric-value">${fmt(glaVal)}</span>`;
    row.appendChild(gla);

    // Visual bar pair (CO blue rule, GLA terracotta rule). Width
    // proportional to value; missing values show a stippled track.
    const bar = document.createElement("div");
    bar.className = "metric-bar";
    const maxV = Math.max(coVal ?? 0, glaVal ?? 0) || 1;
    const coBar = document.createElement("div");
    coBar.className = "bar-track co" + (coVal == null ? " empty" : "");
    if (coVal != null) {
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = `${(coVal / maxV) * 100}%`;
      coBar.appendChild(fill);
    }
    const glaBar = document.createElement("div");
    glaBar.className = "bar-track gla" + (glaVal == null ? " empty" : "");
    if (glaVal != null) {
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = `${(glaVal / maxV) * 100}%`;
      glaBar.appendChild(fill);
    }
    bar.appendChild(coBar);
    bar.appendChild(glaBar);
    row.appendChild(bar);

    const liftCell = document.createElement("div");
    liftCell.className = "metric-lift";
    if (ratioStr) {
      liftCell.innerHTML = `<span class="ratio">${ratioStr}</span>`;
    } else if (diff != null && total) {
      const pct = (diff / total) * 100;
      const sign = pct >= 0 ? "+" : "";
      const cls = diff > 0 ? "pos" : (diff < 0 ? "neg" : "");
      const arrow = diff > 0 ? "▲" : (diff < 0 ? "▼" : "·");
      liftCell.innerHTML = `<span class="${cls}">${arrow} ${sign}${pct.toFixed(0)}${unit}</span>`;
    }
    row.appendChild(liftCell);

    return row;
  }

  /* ---------- Aggregator ---------- */

  function aggregate(pairList) {
    let n = 0, coSolved = 0, glaSolved = 0, coQual = 0, glaQual = 0;
    let coTok = 0, glaTok = 0;
    for (const p of pairList) {
      n += 1;
      if (p.CO.solved) { coSolved += 1; coTok += p.CO.output_tokens || 0; }
      if (p.GLA.solved) { glaSolved += 1; glaTok += p.GLA.output_tokens || 0; }
      if (p.CO.qualified) coQual += 1;
      if (p.GLA.qualified) glaQual += 1;
    }
    return {
      n,
      coSolved, glaSolved,
      coQualified: coQual, glaQualified: glaQual,
      coTokPerSolve: coSolved > 0 ? coTok / coSolved : null,
      glaTokPerSolve: glaSolved > 0 ? glaTok / glaSolved : null,
    };
  }

  /* =================================================================
     SCENARIO TIMELINE GRID  (kept — already a CO|GLA view)
     ================================================================= */

  function renderGrid() {
    const container = document.getElementById("grid-container");
    container.textContent = "";
    const table = document.createElement("table");
    table.className = "timeline";

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

    const thead = document.createElement("thead");
    const trHead = document.createElement("tr");
    trHead.appendChild(elem("th", "scenario"));
    const colKeys = [];
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
    const parts = sid.split("_");
    if (parts.length <= 4) return sid;
    return parts.slice(-4).join(" ");
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
     ROUND NOTES (collapsed; now a minor section)
     ================================================================= */

  function renderCards() {
    const container = document.getElementById("card-container");
    container.textContent = "";
    const ordered = [...rounds].reverse();
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
