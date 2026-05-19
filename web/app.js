const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const els = {
  exampleSelect: $("#exampleSelect"),
  loadExampleButton: $("#loadExampleButton"),
  runButton: $("#runButton"),
  grammarEditor: $("#grammarEditor"),
  lexerEditor: $("#lexerEditor"),
  inputEditor: $("#inputEditor"),
  grammarPath: $("#grammarPath"),
  lexerPath: $("#lexerPath"),
  inputPath: $("#inputPath"),
  verboseToggle: $("#verboseToggle"),
  recoverToggle: $("#recoverToggle"),
  statusPill: $("#statusPill"),
  tokenCount: $("#tokenCount"),
  stateCount: $("#stateCount"),
  stepCount: $("#stepCount"),
  issueCount: $("#issueCount"),
  problemList: $("#problemList"),
  summaryTab: $("#summaryTab"),
  tablesTab: $("#tablesTab"),
  automatonTab: $("#automatonTab"),
  stepsTab: $("#stepsTab"),
  consoleTab: $("#consoleTab"),
  exportJsonButton: $("#exportJsonButton"),
  exportDotButton: $("#exportDotButton"),
};

const state = {
  examples: [],
  currentPaths: {
    grammar: "",
    lexer: "",
    input: "",
  },
  result: null,
};

init();

function init() {
  bindEvents();
  fetchExamples();
}

function bindEvents() {
  els.loadExampleButton.addEventListener("click", loadSelectedExample);
  els.runButton.addEventListener("click", runAnalysis);
  $("#clearGrammarButton").addEventListener("click", () => setEditor("grammar", "", "Sin archivo cargado"));
  $("#clearLexerButton").addEventListener("click", () => setEditor("lexer", "", "Lexer limpio"));
  $("#clearInputButton").addEventListener("click", () => setEditor("input", "", "Entrada limpia"));
  els.exportJsonButton.addEventListener("click", () => exportArtifact("json"));
  els.exportDotButton.addEventListener("click", () => exportArtifact("dot"));

  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });

  $$("input[name='method']").forEach((radio) => {
    radio.addEventListener("change", () => {
      const selected = state.examples.find((example) => example.id === els.exampleSelect.value);
      if (selected) {
        selected.method = getMethod();
      }
    });
  });
}

async function fetchExamples() {
  try {
    const data = await requestJson("/api/examples");
    state.examples = data.examples || [];
    els.exampleSelect.innerHTML = state.examples
      .map((example) => `<option value="${escapeAttr(example.id)}">${escapeHtml(example.title)}</option>`)
      .join("");
    if (state.examples.length) {
      els.exampleSelect.value = state.examples[0].id;
      await loadSelectedExample();
    }
  } catch (error) {
    setStatus("error", "No se pudieron cargar ejemplos");
    els.problemList.innerHTML = problemHtml(String(error), "error");
  }
}

async function loadSelectedExample() {
  const example = state.examples.find((item) => item.id === els.exampleSelect.value);
  if (!example) {
    return;
  }

  setStatus("running", "Cargando");
  setMethod(example.method || "slr");
  try {
    await Promise.all([
      loadFileInto("grammar", example.grammar),
      loadFileInto("lexer", example.lexer),
      loadFileInto("input", example.input),
    ]);
    setStatus("idle", "Listo");
    await runAnalysis();
  } catch (error) {
    setStatus("error", "Error al cargar");
    els.problemList.innerHTML = problemHtml(String(error), "error");
  }
}

async function loadFileInto(kind, path) {
  if (!path) {
    setEditor(kind, "", "Sin archivo");
    return;
  }
  const data = await requestJson(`/api/read?path=${encodeURIComponent(path)}`);
  setEditor(kind, data.text || "", data.path || path);
}

function setEditor(kind, value, label) {
  state.currentPaths[kind] = label || "";
  if (kind === "grammar") {
    els.grammarEditor.value = value;
    els.grammarPath.textContent = label || "Sin archivo cargado";
  }
  if (kind === "lexer") {
    els.lexerEditor.value = value;
    els.lexerPath.textContent = label || "Lexer limpio";
  }
  if (kind === "input") {
    els.inputEditor.value = value;
    els.inputPath.textContent = label || "Entrada limpia";
  }
}

async function runAnalysis() {
  const payload = {
    method: getMethod(),
    verbose: els.verboseToggle.checked,
    recover: els.recoverToggle.checked,
    grammar: els.grammarEditor.value,
    lexer: els.lexerEditor.value,
    input: els.inputEditor.value,
    lexerName: state.currentPaths.lexer || "lexer.yal",
  };

  setStatus("running", "Ejecutando");
  els.runButton.disabled = true;
  try {
    const result = await requestJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.result = result;
    renderResult(result);
    setStatus(result.ok ? "ok" : "error", result.ok ? "Aceptado" : "Revisar");
  } catch (error) {
    state.result = null;
    renderFatalError(error);
    setStatus("error", "Error");
  } finally {
    els.runButton.disabled = false;
  }
}

function renderResult(result) {
  renderMetrics(result);
  renderProblems(result);
  renderSummary(result);
  renderTables(result);
  renderAutomaton(result);
  renderSteps(result);
  renderConsole(result);
  els.exportJsonButton.disabled = !result.artifacts?.json?.content;
  els.exportDotButton.disabled = !result.artifacts?.dot?.content;
}

function renderMetrics(result) {
  const analysis = result.analysis || {};
  const automaton = analysis.automaton || analysis;
  const parse = analysis.parse || {};
  const issueCount = (result.errors || []).length + (result.warnings || []).length;
  els.tokenCount.textContent = String(result.grammar?.tokens?.length || 0);
  els.stateCount.textContent = String(
    analysis.stateCount || analysis.lalrStates || automaton.states?.length || 0,
  );
  els.stepCount.textContent = String(parse.steps?.length || 0);
  els.issueCount.textContent = String(issueCount);
}

function renderProblems(result) {
  const errors = result.errors || [];
  const warnings = result.warnings || [];
  const parts = [
    ...errors.map((item) => problemHtml(item, "error")),
    ...warnings.map((item) => problemHtml(item, "warning")),
  ];
  els.problemList.innerHTML = parts.length
    ? parts.join("")
    : '<p class="muted">Sin problemas detectados.</p>';
}

function renderSummary(result) {
  if (!result.grammar) {
    els.summaryTab.innerHTML = emptyState(result.error || "No se pudo leer la gramatica.");
    return;
  }
  const grammar = result.grammar;
  const analysis = result.analysis || {};
  const parse = analysis.parse;
  const compatible = analysis.isCompatible ?? analysis.isSLR1 ?? analysis.isLALR1 ?? true;
  const accepted = parse ? parse.accepted : null;
  const lexerTokens = result.lexer?.tokens || [];

  els.summaryTab.innerHTML = `
    <div class="summary-grid">
      <section class="info-block">
        <h3>Resultado</h3>
        <p>${statusBadge(compatible, "Gramatica compatible", "Hay conflictos")}</p>
        ${
          accepted === null
            ? '<p class="muted">No hay entrada parseada en esta ejecucion.</p>'
            : `<p>${statusBadge(accepted, "Entrada aceptada", "Entrada rechazada")}</p>`
        }
        ${parse?.error ? `<p class="problem error">${escapeHtml(parse.error)}</p>` : ""}
      </section>

      <section class="info-block">
        <h3>Gramatica</h3>
        <p><strong>Inicio:</strong> <code>${escapeHtml(grammar.startSymbol)}</code></p>
        <p><strong>No terminales:</strong> ${grammar.nonTerminals.length}</p>
        <p><strong>Producciones:</strong> ${grammar.productions.length}</p>
      </section>

      <section class="info-block wide">
        <h3>Tokens declarados</h3>
        <div class="chip-row">${chipList(grammar.tokens)}</div>
      </section>

      <section class="info-block wide">
        <h3>Tokens ignorados</h3>
        <div class="chip-row">${chipList(grammar.ignored, "ignored") || '<span class="muted">Ninguno</span>'}</div>
      </section>

      <section class="info-block wide">
        <h3>Tokens producidos por lexer</h3>
        <div class="chip-row">${chipList(lexerTokens) || '<span class="muted">Sin lexer cargado</span>'}</div>
      </section>

      <section class="info-block wide">
        <h3>Producciones</h3>
        ${simpleTable(["#", "Produccion"], grammar.productions.map((p) => [p.index, `<code>${escapeHtml(p.text)}</code>`]))}
      </section>
    </div>
  `;
}

function renderTables(result) {
  const analysis = result.analysis || {};
  if (analysis.kind === "ll1") {
    els.tablesTab.innerHTML = `
      <div class="summary-grid">
        <section class="info-block wide">
          <h3>FIRST</h3>
          ${mapTable("Simbolo", "FIRST", analysis.first)}
        </section>
        <section class="info-block wide">
          <h3>FOLLOW</h3>
          ${mapTable("Simbolo", "FOLLOW", analysis.follow)}
        </section>
        <section class="info-block wide">
          <h3>Tabla predictiva</h3>
          ${simpleTable(["No terminal", "Lookahead", "Produccion"], (analysis.table || []).map((row) => [
            `<code>${escapeHtml(row.nonTerminal)}</code>`,
            `<code>${escapeHtml(row.terminal)}</code>`,
            row.productions.map((p) => `<code>${escapeHtml(p)}</code>`).join("<br>"),
          ]))}
        </section>
      </div>
    `;
    return;
  }

  if (analysis.kind === "lr0") {
    const automaton = analysis.automaton || {};
    els.tablesTab.innerHTML = `
      <div class="summary-grid">
        <section class="info-block wide">
          <h3>Producciones LR(0)</h3>
          ${simpleTable(["#", "Produccion"], (automaton.productions || []).map((p) => [
            p.index,
            `<code>${escapeHtml(p.lhs)} -> ${escapeHtml((p.rhs || []).join(" ") || "epsilon")}</code>`,
          ]))}
        </section>
        <section class="info-block wide">
          <h3>Transiciones</h3>
          ${transitionTable(automaton.transitions || [])}
        </section>
      </div>
    `;
    return;
  }

  const actionRows = (analysis.action || []).map((row) => [
    row.state,
    `<code>${escapeHtml(row.terminal)}</code>`,
    `<code>${escapeHtml(row.action)}</code>`,
  ]);
  const gotoRows = (analysis.goto || []).map((row) => [
    row.state,
    `<code>${escapeHtml(row.nonTerminal)}</code>`,
    row.to,
  ]);
  els.tablesTab.innerHTML = `
    <div class="summary-grid">
      <section class="info-block wide">
        <h3>ACTION</h3>
        ${simpleTable(["Estado", "Terminal", "Accion"], actionRows)}
      </section>
      <section class="info-block wide">
        <h3>GOTO</h3>
        ${simpleTable(["Estado", "No terminal", "Destino"], gotoRows)}
      </section>
      <section class="info-block wide">
        <h3>Conflictos</h3>
        ${(analysis.conflicts || []).length ? (analysis.conflicts || []).map((item) => problemHtml(String(item), "error")).join("") : '<p class="muted">Sin conflictos.</p>'}
      </section>
    </div>
  `;
}

function renderAutomaton(result) {
  const analysis = result.analysis || {};
  const automaton = analysis.automaton || (analysis.states ? analysis : null);
  if (!automaton?.states?.length) {
    els.automatonTab.innerHTML = emptyState("Este metodo no genero automata visible.");
    return;
  }

  els.automatonTab.innerHTML = `
    <div class="automaton-shell">
      <div class="graph-toolbar">
        <span class="badge info">${automaton.states.length} estados</span>
        <span class="muted">${(automaton.transitions || []).length} transiciones</span>
      </div>
      <div class="graph-stage">${graphSvg(automaton)}</div>
      <section class="info-block">
        <h3>Estados</h3>
        ${stateTable(automaton.states)}
      </section>
    </div>
  `;
}

function renderSteps(result) {
  const analysis = result.analysis || {};
  const parse = analysis.parse;
  const lexerTokens = result.lexer?.output?.tokens || [];
  if (!parse) {
    els.stepsTab.innerHTML = emptyState("Carga lexer e input para ejecutar el parser.");
    return;
  }

  els.stepsTab.innerHTML = `
    <div class="summary-grid">
      <section class="info-block wide">
        <h3>Tokens de entrada</h3>
        ${simpleTable(["#", "Tipo", "Lexema", "Linea", "Columna"], lexerTokens.map((token, index) => [
          index + 1,
          `<code>${escapeHtml(token.type)}</code>`,
          `<code>${escapeHtml(JSON.stringify(token.lexeme))}</code>`,
          token.line,
          token.column,
        ]))}
      </section>
      <section class="info-block wide">
        <h3>Pasos del parser</h3>
        ${parse.steps?.length ? simpleTable(["#", "Stack", "Lookahead", "Accion"], parse.steps.map((step, index) => [
          index + 1,
          `<code>${escapeHtml(JSON.stringify(step.stack))}</code>`,
          `<code>${escapeHtml(step.lookahead)}</code>`,
          `<code>${escapeHtml(step.action)}</code>`,
        ])) : '<p class="muted">Activa "Mostrar pasos" para ver la traza completa.</p>'}
      </section>
      ${
        parse.errors?.length
          ? `<section class="info-block wide"><h3>Errores recuperados</h3>${parse.errors.map((item) => problemHtml(item, "error")).join("")}</section>`
          : ""
      }
    </div>
  `;
}

function renderConsole(result) {
  els.consoleTab.innerHTML = `<pre>${escapeHtml(result.console || result.error || "Sin salida.")}</pre>`;
}

function renderFatalError(error) {
  const message = String(error);
  els.summaryTab.innerHTML = emptyState(message);
  els.tablesTab.innerHTML = emptyState("No hay tablas disponibles.");
  els.automatonTab.innerHTML = emptyState("No hay automata disponible.");
  els.stepsTab.innerHTML = emptyState("No hay pasos disponibles.");
  els.consoleTab.innerHTML = `<pre>${escapeHtml(message)}</pre>`;
  els.problemList.innerHTML = problemHtml(message, "error");
  renderMetrics({ errors: [message] });
}

function activateTab(name) {
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  $$(".tab-content").forEach((panel) => panel.classList.remove("active"));
  $(`#${name}Tab`).classList.add("active");
}

function getMethod() {
  return $("input[name='method']:checked")?.value || "slr";
}

function setMethod(method) {
  const radio = $(`input[name='method'][value='${method}']`);
  if (radio) {
    radio.checked = true;
  }
}

function setStatus(kind, text) {
  els.statusPill.className = `status-pill ${kind}`;
  els.statusPill.textContent = text;
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function exportArtifact(kind) {
  const artifact = state.result?.artifacts?.[kind];
  if (!artifact?.content) {
    return;
  }
  const extension = kind === "dot" ? "dot" : "json";
  const filename = `yapar_${getMethod()}_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.${extension}`;
  const type = kind === "dot" ? "text/vnd.graphviz" : "application/json";
  downloadText(filename, artifact.content, type);
}

function downloadText(filename, content, type) {
  const blob = new Blob([content], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function statusBadge(ok, yes, no) {
  return `<span class="badge ${ok ? "ok" : "error"}">${escapeHtml(ok ? yes : no)}</span>`;
}

function chipList(items, extraClass = "") {
  return (items || [])
    .map((item) => `<span class="chip ${extraClass}">${escapeHtml(item)}</span>`)
    .join("");
}

function mapTable(leftLabel, rightLabel, values) {
  const rows = Object.entries(values || {}).map(([key, list]) => [
    `<code>${escapeHtml(key)}</code>`,
    `<code>${escapeHtml((list || []).join(", ") || "vacio")}</code>`,
  ]);
  return simpleTable([leftLabel, rightLabel], rows);
}

function transitionTable(transitions) {
  return simpleTable(["Desde", "Simbolo", "Hacia"], transitions.map((row) => [
    row.from,
    `<code>${escapeHtml(row.symbol)}</code>`,
    row.to,
  ]));
}

function stateTable(states) {
  return simpleTable(["Estado", "Items"], (states || []).map((stateItem) => [
    `<strong>I${escapeHtml(String(stateItem.id))}</strong>`,
    (stateItem.items || []).map((item) => `<code>${escapeHtml(item)}</code>`).join("<br>"),
  ]));
}

function simpleTable(headers, rows) {
  if (!rows?.length) {
    return '<p class="muted">Sin datos.</p>';
  }
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(String(header))}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function graphSvg(automaton) {
  const states = automaton.states || [];
  const transitions = automaton.transitions || [];
  const nodeW = 220;
  const nodeH = 106;
  const gapX = 88;
  const gapY = 82;
  const cols = Math.max(1, Math.ceil(Math.sqrt(states.length)));
  const rows = Math.ceil(states.length / cols);
  const width = Math.max(760, 60 + cols * nodeW + (cols - 1) * gapX + 60);
  const height = Math.max(420, 60 + rows * nodeH + (rows - 1) * gapY + 60);
  const positions = new Map();

  states.forEach((stateItem, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    positions.set(stateItem.id, {
      x: 60 + col * (nodeW + gapX),
      y: 60 + row * (nodeH + gapY),
    });
  });

  const edgeMarkup = transitions
    .map((edge, index) => {
      const from = positions.get(edge.from);
      const to = positions.get(edge.to);
      if (!from || !to) {
        return "";
      }
      const startX = from.x + nodeW;
      const startY = from.y + nodeH / 2;
      const endX = to.x;
      const endY = to.y + nodeH / 2;
      const labelX = (startX + endX) / 2;
      const labelY = (startY + endY) / 2 - 8;
      if (edge.from === edge.to) {
        const loopX = from.x + nodeW / 2;
        const loopY = from.y - 24;
        return `
          <path class="edge" marker-end="url(#arrow)" d="M ${from.x + nodeW * 0.7} ${from.y} C ${from.x + nodeW + 36} ${loopY}, ${from.x - 36} ${loopY}, ${from.x + nodeW * 0.3} ${from.y}" />
          <text class="edge-label" x="${loopX}" y="${loopY - 5}" text-anchor="middle">${escapeSvg(edge.symbol)}</text>
        `;
      }
      const curve = Math.abs(edge.to - edge.from) > 1 ? 42 : 12;
      return `
        <path class="edge" marker-end="url(#arrow)" d="M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}" />
        <text class="edge-label" x="${labelX}" y="${labelY}" text-anchor="middle">${escapeSvg(edge.symbol)}</text>
      `;
    })
    .join("");

  const nodeMarkup = states
    .map((stateItem) => {
      const pos = positions.get(stateItem.id);
      const items = (stateItem.items || []).slice(0, 4);
      const hidden = Math.max(0, (stateItem.items || []).length - items.length);
      const lines = [
        `<text x="${pos.x + 12}" y="${pos.y + 23}" font-weight="800">I${escapeSvg(String(stateItem.id))}</text>`,
        ...items.map((item, i) => {
          const text = truncateMiddle(item, 34);
          return `<text x="${pos.x + 12}" y="${pos.y + 45 + i * 15}">${escapeSvg(text)}</text>`;
        }),
      ];
      if (hidden) {
        lines.push(`<text x="${pos.x + 12}" y="${pos.y + 45 + items.length * 15}" fill="#617073">+${hidden} mas</text>`);
      }
      return `
        <g class="node">
          <rect x="${pos.x}" y="${pos.y}" width="${nodeW}" height="${nodeH}"></rect>
          ${lines.join("")}
        </g>
      `;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Automata de analisis">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z" fill="#6f7f82"></path>
        </marker>
      </defs>
      ${edgeMarkup}
      ${nodeMarkup}
    </svg>
  `;
}

function problemHtml(item, kind) {
  return `<div class="problem ${kind === "error" ? "error" : ""}">${escapeHtml(String(item))}</div>`;
}

function emptyState(message) {
  return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function truncateMiddle(value, size) {
  const text = String(value);
  if (text.length <= size) {
    return text;
  }
  const keep = Math.max(4, Math.floor((size - 3) / 2));
  return `${text.slice(0, keep)}...${text.slice(-keep)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function escapeSvg(value) {
  return escapeHtml(value);
}
