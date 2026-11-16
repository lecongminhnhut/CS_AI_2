import { makePortrait } from "./portraits.js";

const $ = (id) => document.getElementById(id);
const board = $("board");
const desk = $("desk");
const verdictDialog = $("verdict-dialog");
const verdictChoices = $("verdict-choices");
const verdictDismiss = $("verdict-dismiss");
const cards = new Map();
let state, activeCard, activeTerm, visibleClue, hintCell, syncScene, verdictCard;
let hoveredWord = null;
let pendingHintCell = null;
let hintSources = [];
let busy = false;
let running = false;
let pauseRequested = false;

const messages = {
  NOT_PROVABLE: "NOT_PROVABLE · The visible clues allow either verdict.",
  CONTRADICTED: "CONTRADICTED · The visible clues prove the opposite verdict.",
  INCONSISTENT: "INCONSISTENT · The visible evidence conflicts.",
  UNKNOWN: "UNKNOWN · The visible evidence does not prove any remaining verdict.",
  SOLVED: "Case solved. Every verdict was proved.",
  ALREADY_REVEALED: "This card is already open.",
};

const clueColors = ["#87e7ff", "#ffd17d", "#f2a6e0", "#b8ed8e"];
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function ringElement(tag, className) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  if (className) node.setAttribute("class", className);
  return node;
}

function paintRing(ring, colors) {
  const key = colors.join(",");
  if ((ring.dataset.colors ?? "") === key) return;
  ring.dataset.colors = key;
  const strokes = colors.map((color, index) => {
    const stroke = ringElement("rect");
    stroke.setAttribute("stroke", color);
    stroke.setAttribute("pathLength", "100");
    if (colors.length > 1) {
      const length = 100 / colors.length;
      stroke.setAttribute("stroke-dasharray", `${length + .2} ${100 - length - .2}`);
      stroke.setAttribute("stroke-dashoffset", String(-index * length));
    }
    return stroke;
  });
  ring.children[0].replaceChildren(...strokes.map(stroke => stroke.cloneNode()));
  ring.children[1].replaceChildren(...strokes);
}

async function api(route, body) {
  const response = await fetch(`/api/${route}`, body === undefined ? undefined : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Unable to reach the game engine.");
  return result;
}

function notice(text = "", error = false) {
  $("notice").textContent = text;
  $("notice").dataset.error = String(error);
}

function updateTools() {
  $("cases").disabled = !state || busy || running;
  $("restart").disabled = !state || busy || running;
  $("hint").disabled = !state || busy || running || state.terminal === "SOLVED";
  $("hint").textContent = hintCell ? "Clear" : pendingHintCell ? "Reveal" : "Hint";
  $("auto").disabled = !state || busy || pauseRequested || (!running && Boolean(state.terminal));
  $("auto").textContent = pauseRequested ? "Pausing…" : running ? "Ⅱ  Pause" : "▷  Auto solve";
  for (const button of verdictDialog.querySelectorAll("button")) button.disabled = busy || running;
}

function clearHint() {
  pendingHintCell = null;
  hintCell = null;
  hintSources = [];
}

function makeBoard() {
  cards.clear();
  board.replaceChildren();
  board.style.setProperty("--side", state.size);
  board.dataset.size = state.size;
  for (const [index, card] of state.cards.entries()) {
    const frame = element("div", "card");
    frame.dataset.cell = card.cell;
    const button = element("button", "card-action");
    button.type = "button";
    const portrait = element("span", "card-portrait");
    portrait.append(makePortrait(card, index));
    const status = element("span", "card-status");
    const identity = element("span", "card-identity");
    identity.append(element("span", "card-name", card.name),
      element("span", "card-profession", card.profession));
    button.append(portrait, element("span", "card-coordinate", card.cell), identity);
    const clue = element("div", "card-clue");
    const ring = ringElement("svg", "reference-ring");
    ring.append(ringElement("g", "reference-halo"), ringElement("g", "reference-line"));
    ring.setAttribute("aria-hidden", "true");
    frame.addEventListener("click", event => {
      if (!event.target.closest(".clue-word")) selectCard(card.cell);
    });
    frame.append(button, clue, status, ring);
    board.append(frame);
    cards.set(card.cell, { frame, button, status, clue, ring });
  }
}

function selectCard(cell) {
  const card = state.cards.find(item => item.cell === cell);
  if (card.clue) {
    spotlight(activeCard === cell ? null : cell);
  } else if (!busy && !running) {
    openVerdict(card);
  }
}

function spotlight(cell, term = null) {
  hoveredWord = null;
  if (activeCard === cell && activeTerm === term) {
    if (term === null) activeCard = null;
    activeTerm = null;
  } else {
    activeCard = cell;
    activeTerm = term;
  }
  const targets = updateCards();
  syncScene?.();
  renderDesk();
  $("clue-signal").textContent = targets.size
    ? `Highlighted cells: ${[...targets.keys()].join(", ")}.`
    : "";
}

function fillClue(container, card) {
  const sentence = element("p", "clue-text");
  const onCard = container.classList.contains("card-clue");
  for (const { part, key, color } of coloredParts(card.clue)) {
    if (!part.cells) {
      sentence.append(document.createTextNode(part.text));
      continue;
    }
    const token = element(onCard ? "span" : "button", "clue-word", part.text);
    token.style.setProperty("--clue-color", color);
    if (onCard) {
      token.setAttribute("role", "button");
      token.tabIndex = 0;
      token.addEventListener("keydown", event => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        if (!event.repeat) token.click();
      });
    } else {
      token.type = "button";
    }
    token.dataset.clueword = key;
    token.setAttribute("aria-pressed", String(activeCard === card.cell && activeTerm === key));
    token.addEventListener("pointerenter", event => {
      if (event.pointerType !== "mouse") return;
      hoveredWord = { token, cells: part.cells, color };
      updateHighlights();
      syncScene?.();
    });
    token.addEventListener("pointerleave", () => {
      if (hoveredWord?.token !== token) return;
      hoveredWord = null;
      updateHighlights();
      syncScene?.();
    });
    token.addEventListener("click", () => spotlight(card.cell, key));
    sentence.append(token);
  }
  container.append(sentence);
}

function fitCardClue(clue) {
  const sentence = clue.firstElementChild;
  if (clue.hidden || !sentence || !clue.clientWidth) return;

  clue.style.removeProperty("font-size");
  const style = getComputedStyle(clue);
  const card = clue.closest(".card");
  const cardStyle = getComputedStyle(card);
  const action = card.querySelector(".card-action");
  const identity = action.querySelector(".card-identity");
  const status = card.querySelector(".card-status");
  const freeSpace = card.clientHeight - parseFloat(cardStyle.paddingBlockStart)
    - parseFloat(cardStyle.paddingBlockEnd) - 2 * parseFloat(cardStyle.rowGap)
    - identity.offsetHeight - status.offsetHeight - parseFloat(getComputedStyle(action).rowGap) - 1;
  const available = Math.min(parseFloat(style.maxBlockSize), freeSpace) - parseFloat(style.borderTopWidth)
    - parseFloat(style.paddingBlockStart) - parseFloat(style.paddingBlockEnd);
  const fits = () => parseFloat(getComputedStyle(sentence).height) <= available
    && sentence.scrollWidth <= sentence.clientWidth;
  if (fits()) return;

  let smallest = 1;
  let largest = parseFloat(style.fontSize);
  while (largest - smallest > .15) {
    const size = (smallest + largest) / 2;
    clue.style.fontSize = `${size}px`;
    if (fits()) smallest = size;
    else largest = size;
  }
  clue.style.fontSize = `${smallest}px`;
}

function fitBoardClues() {
  for (const { clue } of cards.values()) fitCardClue(clue);
}

function coloredParts(clue) {
  let colorIndex = 0;
  return clue.parts.map((part, index) => {
    const color = part.cells ? clueColors[colorIndex++] : null;
    return { part, key: `${clue.id}:${index}`, color };
  });
}

function updateWords(container, cell) {
  for (const word of container.querySelectorAll(".clue-word")) {
    word.setAttribute("aria-pressed", String(activeCard === cell && word.dataset.clueword === activeTerm));
  }
}

function updateHighlights() {
  const active = state.cards.find(card => card.cell === activeCard);
  const references = new Map();
  if (hoveredWord) {
    const { cells, color } = hoveredWord;
    for (const cell of cells) references.set(cell, [color]);
  } else if (active?.clue) {
    for (const { part, key, color } of coloredParts(active.clue)) {
      if (!part.cells || (activeTerm !== null && activeTerm !== key)) continue;
      for (const cell of part.cells) {
        if (!references.has(cell)) references.set(cell, []);
        references.get(cell).push(color);
      }
    }
  }
  for (const [cell, { frame, ring }] of cards) {
    const colors = references.get(cell) ?? [];
    const spotlit = active?.cell === cell;
    const isReference = references.has(cell);
    frame.classList.toggle("spotlit", spotlit);
    frame.classList.toggle("referenced", isReference);
    frame.classList.toggle("dimmed", Boolean(active) && !spotlit && !isReference
      && !hintSources.includes(cell) && cell !== hintCell);
    paintRing(ring, colors);
  }
  return references;
}

function updateCards() {
  for (const card of state.cards) {
    const { frame, button, status, clue } = cards.get(card.cell);
    const key = card.status?.toLowerCase() ?? "hidden";
    frame.dataset.status = key;
    for (const stateClass of ["hidden", "innocent", "criminal"]) {
      frame.classList.toggle(stateClass, stateClass === key);
    }
    frame.classList.toggle("hinted", card.cell === hintCell);
    frame.classList.toggle("hint-source", hintSources.includes(card.cell));
    status.textContent = key;
    clue.hidden = !card.clue;
    const label = `${card.cell} ${card.name}, ${card.profession}, ${key}`;
    if (card.clue) {
      const { text } = card.clue;
      if (clue.dataset.view !== text) {
        clue.dataset.view = text;
        clue.replaceChildren();
        fillClue(clue, card);
        fitCardClue(clue);
      }
      updateWords(clue, card.cell);
      button.removeAttribute("aria-haspopup");
      button.setAttribute("aria-pressed", String(activeCard === card.cell));
      button.setAttribute("aria-label", `${label}. ${text}`);
    } else {
      clue.dataset.view = "";
      clue.replaceChildren();
      button.setAttribute("aria-haspopup", "dialog");
      button.removeAttribute("aria-pressed");
      button.setAttribute("aria-label", `${label}. Choose a verdict.`);
    }
  }
  return updateHighlights();
}

function renderDesk() {
  const focused = desk.contains(document.activeElement) ? document.activeElement.dataset : {};
  const scroll = desk.querySelector(".clue-list")?.scrollTop ?? 0;
  const slot = element("div", "desk-selection");
  const card = state.cards.find(item => item.cell === activeCard);
  if (card) visibleClue = card.cell;
  const current = Math.max(0, state.opened.indexOf(visibleClue));
  const count = state.opened.length;
  $("clue-position").textContent = `${count ? current + 1 : 0} / ${count}`;
  $("clue-prev").disabled = current === 0;
  $("clue-next").disabled = current + 1 >= count;
  if (card) {
    const clear = element("button", "quiet clear-clue", "Clear");
    clear.type = "button";
    clear.setAttribute("aria-label", "Clear clue spotlight");
    clear.addEventListener("click", () => {
      spotlight(null);
      cards.get(card.cell).button.focus({ preventScroll: true });
    });
    slot.append(element("h3", "", `${card.name} · ${card.cell}`), clear);
  } else {
    slot.append(element("p", "", "Select a clue or an underlined term to highlight its cards."));
  }
  const list = element("div", "clue-list");
  for (const cell of state.opened) {
    const owner = state.cards.find(item => item.cell === cell);
    const entry = element("article", "clue");
    entry.classList.toggle("clue-active", activeCard === cell);
    entry.classList.toggle("hint-source", hintSources.includes(cell));
    entry.classList.toggle("clue-current", cell === state.opened[current]);
    const button = element("button", "clue-label", `${owner.cell} · `);
    button.append(element("span", "clue-owner", owner.name));
    button.type = "button";
    button.dataset.clue = cell;
    button.setAttribute("aria-pressed", String(activeCard === cell && activeTerm === null));
    button.addEventListener("click", () => spotlight(cell));
    entry.append(button);
    fillClue(entry, owner);
    list.append(entry);
  }
  desk.replaceChildren(slot, list);
  list.scrollTop = scroll;
  const key = focused.clueword ? "clueword" : "clue";
  if (focused[key]) {
    [...list.querySelectorAll(`[data-${key}]`)].find(node => node.dataset[key] === focused[key])
      ?.focus({ preventScroll: true });
  }
  const entry = list.querySelector(`[data-clue="${activeCard ?? hintSources[0]}"]`)?.closest(".clue");
  if (entry) {
    const offset = entry.getBoundingClientRect().top - list.getBoundingClientRect().top;
    if (offset < 0) list.scrollTop += offset;
    else if (offset + entry.offsetHeight > list.clientHeight) {
      list.scrollTop += offset + entry.offsetHeight - list.clientHeight;
    }
  }
  updateTools();
}

function browseClues(offset) {
  const index = Math.max(0, state.opened.indexOf(visibleClue));
  const cell = state.opened[index + offset];
  if (cell) spotlight(cell);
}

function renderTrace(reset) {
  const log = $("trace-list");
  if (reset) log.replaceChildren();
  for (const trace of state.trace.slice(log.children.length)) {
    const item = element("li", "");
    const detail = element("details", "");
    const summary = element("summary", "", trace.cell);
    const character = state.cards.find(card => card.cell === trace.cell);
    if (character) summary.append(" · ", element("span", "trace-name", character.name));
    summary.append(` → ${trace.verdict.toLowerCase()} · ${trace.mode}`);
    detail.append(summary,
      element("p", "", `Active clues: ${trace.active_clues.join(", ")}`));
    const queries = element("ul", "");
    for (const query of trace.queries) {
      const assumption = query.cell ? ` + ${query.cell} ${query.assumed.toLowerCase()}` : "";
      queries.append(element("li", "", `KB${assumption} → ${query.result}`));
    }
    detail.append(queries, element("p", "", `Revealed: ${trace.revealed.text}`));
    item.append(detail);
    log.append(item);
  }
  const stats = state.stats;
  $("trace-count").textContent = `${state.trace.length} ${state.trace.length === 1 ? "step" : "steps"}`;
  const labels = [
    ["variables", "primary"], ["auxiliary", "aux"], ["clauses", "clauses"],
    ["calls", "SAT calls"], ["decisions", "decisions"],
    ["propagations", "propagations"], ["backtracks", "backtracks"], ["runtime_ms", "ms SAT"],
  ];
  $("stats").replaceChildren(...labels.filter(([key]) => Number.isFinite(stats[key])).map(([key, label]) =>
    element("span", "", `${key === "runtime_ms" ? stats[key].toFixed(1) : stats[key]} ${label}`)));
}

function render(next, { reset = false, revealed } = {}) {
  hoveredWord = null;
  const rebuild = !state || state.id !== next.id;
  state = next;
  if (rebuild) makeBoard();
  if (reset || rebuild) {
    activeCard = null;
    activeTerm = null;
    visibleClue = null;
    clearHint();
  }
  if (revealed) {
    activeCard = revealed;
    activeTerm = null;
    clearHint();
  }
  $("loading").hidden = true;
  $("case-number").textContent = `CASE FILE / ${String($("cases").selectedIndex + 1).padStart(2, "0")}`;
  $("case-title").textContent = state.title;
  $("progress").max = state.cards.length;
  $("progress").value = state.opened.length;
  $("progress-text").textContent = `${state.opened.length} / ${state.cards.length} revealed`;
  updateCards();
  syncScene?.();
  renderDesk();
  renderTrace(reset);
}

async function revealCard(next, cell) {
  const frame = cards.get(cell)?.frame;
  if (!frame || reduceMotion.matches || !frame.animate) {
    render(next, { revealed: cell });
    return;
  }
  frame.classList.add("flipping");
  syncScene?.();
  const close = frame.animate(
    [{ transform: "none" }, { transform: "scaleX(.045) scaleY(.985)", opacity: .32 }],
    { duration: 135, easing: "ease-in", fill: "forwards" },
  );
  try {
    await close.finished;
    render(next, { revealed: cell });
    const innocent = frame.dataset.status === "innocent";
    frame.classList.add(innocent ? "reveal-innocent" : "reveal-criminal");
    const open = frame.animate([
      { transform: "scaleX(.045) scaleY(.985)", opacity: .32 },
      { transform: innocent ? "translateY(-5px) scale(1.025)" : "scale(1.05, .98)", offset: .72 },
      { transform: "none", opacity: 1 },
    ], { duration: innocent ? 335 : 250, easing: "cubic-bezier(.18,.7,.28,1)" });
    close.cancel();
    await open.finished;
  } finally {
    close.cancel();
    frame.classList.remove("flipping", "reveal-innocent", "reveal-criminal");
    syncScene?.();
  }
}

async function action(route, data, receive, reportError = message => notice(message, true)) {
  if (busy || running) return;
  busy = true;
  updateTools();
  try {
    await receive(await api(route, data));
  } catch (error) {
    reportError(error.message);
  } finally {
    busy = false;
    updateTools();
  }
}

function openVerdict(card) {
  verdictCard = card;
  $("verdict-label").textContent = `${card.cell} · ${card.profession}`;
  $("verdict-title").textContent = card.name;
  $("verdict-description").textContent = "Innocent or criminal? Choose the verdict the visible clues prove.";
  $("verdict-status").hidden = true;
  verdictChoices.hidden = false;
  verdictDismiss.textContent = "Cancel";
  verdictDialog.showModal();
}

function submit(verdict) {
  const { cell, name } = verdictCard;
  const status = $("verdict-status");
  status.textContent = "Checking the visible evidence…";
  status.dataset.error = "false";
  status.hidden = false;
  action("verdict", { cell_id: cell, status: verdict }, async ({ state: next, result }) => {
    if (result === "ACCEPTED") {
      verdictDialog.close();
      await revealCard(next, cell);
      cards.get(cell).button.focus({ preventScroll: true });
      notice(next.terminal === "SOLVED" ? messages.SOLVED : `${cell} proved ${verdict.toLowerCase()}. Clue revealed.`);
    } else {
      const text = messages[result] ?? "This card is already open.";
      const choice = verdict.toLowerCase();
      const other = verdict === "CRIMINAL" ? "innocent" : "criminal";
      const feedback = {
        NOT_PROVABLE: ["Conclusion not possible", `The revealed clues still allow ${name} to be ${other}. Read more clues before calling ${name} ${choice}.`],
        CONTRADICTED: ["The clues say otherwise", `The revealed clues prove ${name} is ${other}.`],
      }[result] ?? ["Verdict declined", text];
      render(next);
      notice(text, true);
      $("verdict-label").textContent = result;
      $("verdict-title").textContent = feedback[0];
      $("verdict-description").textContent = feedback[1];
      status.hidden = true;
      verdictChoices.hidden = true;
      verdictDismiss.textContent = "Keep looking";
    }
  }, message => {
    status.textContent = message;
    status.dataset.error = "true";
  }).finally(() => {
    if (verdictDialog.open) {
      const target = verdictChoices.hidden ? verdictDismiss : verdictChoices.querySelector(`[data-verdict="${verdict}"]`);
      target.focus();
    }
  });
}

async function autoSolve() {
  if (running) {
    pauseRequested = true;
    updateTools();
    return;
  }
  running = true;
  updateTools();
  try {
    while (!pauseRequested) {
      const { state: next, result } = await api("step", {});
      const last = result === "ACCEPTED" ? next.trace.at(-1) : null;
      if (last) await revealCard(next, last.cell);
      else render(next);
      if (next.terminal || !last) {
        notice(messages[next.terminal ?? result], next.terminal !== "SOLVED");
        return;
      }
      notice(`Step ${last.step} · ${last.cell} proved ${last.verdict.toLowerCase()}.`);
      const wait = reduceMotion.matches ? 50 : 120;
      await new Promise(resolve => setTimeout(resolve, wait));
    }
    notice("Auto solve paused.");
  } catch (error) {
    notice(error.message, true);
  } finally {
    running = false;
    pauseRequested = false;
    updateTools();
  }
}

$("cases").addEventListener("change", event => {
  const id = event.target.value;
  action("load", { puzzle_id: id }, ({ state }) => {
    render(state, { reset: true });
    notice("Case loaded.");
  }, message => {
    $("cases").value = state.id;
    notice(message, true);
  });
});
$("restart").addEventListener("click", () => action("restart", {}, ({ state }) => {
  render(state, { reset: true });
  $("cases").value = state.id;
  notice("Case restarted.");
}));
$("hint").addEventListener("click", () => {
  if (hintCell) {
    clearHint();
    notice("");
    render(state);
    return;
  }
  if (pendingHintCell) {
    hintCell = pendingHintCell;
    const target = state.cards.find(card => card.cell === hintCell);
    notice(`Work out the verdict for ${target.name} (${hintCell}).`);
    render(state);
    return;
  }
  action("hint", {}, ({ state: next, result, cell, clue_cells, hint_scope }) => {
    clearHint();
    if (cell) {
      pendingHintCell = cell;
      hintSources = clue_cells;
      activeCard = null;
      activeTerm = null;
      visibleClue = clue_cells[0];
      const label = clue_cells.length === 1 ? "clue" : "clues";
      notice(hint_scope === "ALL_REVEALED" ? "Review the visible clues before pressing Reveal."
        : `Read the highlighted ${label} on ${clue_cells.join(", ")}.`);
    } else {
      notice(messages[result], true);
    }
    render(next);
  });
});
$("auto").addEventListener("click", autoSolve);
$("help").addEventListener("click", () => $("help-dialog").showModal());
$("show-trace").addEventListener("click", () => $("trace-dialog").showModal());
$("clue-prev").addEventListener("click", () => browseClues(-1));
$("clue-next").addEventListener("click", () => browseClues(1));
board.addEventListener("click", event => {
  if (activeCard && !event.target.closest(".card")) spotlight(null);
});
verdictChoices.addEventListener("click", event => {
  const choice = event.target.closest("[data-verdict]");
  if (choice && !busy) submit(choice.dataset.verdict);
});
verdictDismiss.addEventListener("click", () => verdictDialog.close());
verdictDialog.addEventListener("cancel", event => {
  if (busy) event.preventDefault();
});
verdictDialog.addEventListener("click", event => {
  if (event.target === verdictDialog && !busy) verdictDialog.close();
});

async function start() {
  try {
    const [{ puzzles }, { state }] = await Promise.all([api("puzzles"), api("state")]);
    $("cases").replaceChildren(...puzzles.map(puzzle =>
      new Option(`${puzzle.title} · ${puzzle.size}×${puzzle.size}`, puzzle.id)));
    $("cases").value = state.id;
    render(state, { reset: true });
  } catch (error) {
    $("loading").textContent = error.message;
    return;
  }
  try {
    const { mountBoard } = await import("./board3d.js");
    syncScene = mountBoard($("three-layer"), board);
    syncScene();
  } catch (error) {
    console.info("Using the HTML caseboard.", error.message);
  }
}

const boardResize = new ResizeObserver(fitBoardClues);
boardResize.observe(board);
document.fonts.ready.then(fitBoardClues);
start();

