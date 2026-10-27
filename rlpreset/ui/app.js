"use strict";

const $ = (id) => document.getElementById(id);
const state = { presets: [], selected: new Set(), shown: [], secondsPerPreset: 25 };
const FILTERS = [
  ["f-player", "player", "All players"],
  ["f-body", "body", "Any body"],
  ["f-decal", "decal", "Any decal"],
  ["f-wheels", "wheels", "Any wheels"],
  ["f-boost", "boost", "Any boost"],
];
const STATUS_BOXES = { full: "s-full", partial: "s-partial", cant: "s-cant", unknown: "s-unknown" };
const SLOT_NAMES = {
  body: "Body", decal: "Decal", wheels: "Wheels", boost: "Boost", trail: "Trail",
  goal_explosion: "Goal explosion", primary_finish: "Primary finish", accent_finish: "Accent finish",
  primary_colour: "Primary colour", accent_colour: "Accent colour",
};

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c) node.append(c);
  return node;
}

function api() { return window.pywebview.api; }

function minutes(seconds) {
  if (seconds < 60) return "under a minute";
  const m = Math.round(seconds / 60);
  return `about ${m} min`;
}

// ---------- loading ----------

async function load() {
  const s = await api().get_state();
  state.presets = s.presets;
  state.secondsPerPreset = s.seconds_per_preset;
  const ids = new Set(s.presets.map((p) => p.id));
  for (const id of [...state.selected]) if (!ids.has(id)) state.selected.delete(id);
  showGame(s.game);
  fillFilters();
  render();
}

function showGame(g) {
  const pill = $("game-pill");
  pill.textContent = g.text;
  pill.className = "pill " + (g.found ? (g.ok ? "ok" : "bad") : "");
  $("launch-box").hidden = g.found;
  if (g.launcher) $("launcher").value = g.launcher;
}

function fillFilters() {
  for (const [id, key, anyLabel] of FILTERS) {
    const select = $(id);
    const current = select.value;
    const counts = new Map();
    for (const p of state.presets) if (p[key]) counts.set(p[key], (counts.get(p[key]) || 0) + 1);
    const names = [...counts.keys()].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    select.replaceChildren(el("option", { value: "", text: anyLabel }),
      ...names.map((n) => el("option", { value: n, text: `${n} (${counts.get(n)})` })));
    select.value = names.includes(current) ? current : "";
  }
}

// ---------- grid ----------

function matches(p) {
  for (const [id, key] of FILTERS) {
    const v = $(id).value;
    if (v && p[key] !== v) return false;
  }
  if (p.added && !$("s-added").checked) return false;
  return $(STATUS_BOXES[p.ownership.status]).checked;
}

function carImage(p, team) {
  const box = el("div", { class: `car ${team}` });
  if (p[`has_${team}`]) {
    box.append(el("img", { src: `/img/${p.id}-${team}.webp`, alt: `${p.name} ${team} car`, loading: "lazy", decoding: "async" }));
  } else {
    box.append(el("div", { class: "none", text: "No picture" }));
  }
  return box;
}

function badge(p) {
  if (p.added) return el("span", { class: "badge added", text: "Added" });
  const o = p.ownership;
  if (o.status === "full") return el("span", { class: "badge full", text: "Full" });
  if (o.status === "partial") return el("span", { class: "badge partial", text: `Partial · ${o.owned}/${o.total}` });
  if (o.status === "cant") return el("span", { class: "badge cant", text: "Can't make" });
  return null;
}

function card(p) {
  const node = el("div", { class: "card", tabindex: "0", role: "checkbox", "data-id": p.id });
  const items = [p.body, p.wheels, p.boost].filter(Boolean).join(" · ");
  const missing = p.ownership.missing.length ? `Missing: ${p.ownership.missing.join(", ")}` : "";
  node.title = missing;
  node.append(
    el("div", { class: "cars" }, carImage(p, "blue"), carImage(p, "orange")),
    el("div", { class: "card-title" }, el("span", { class: "name", text: p.name }), el("span", { class: "tick" })),
    el("div", { class: "card-meta" }, badge(p), el("span", { class: "items", text: items })),
  );
  setSelected(node, state.selected.has(p.id));
  return node;
}

function setSelected(node, on) {
  node.classList.toggle("selected", on);
  node.setAttribute("aria-checked", on ? "true" : "false");
}

function render() {
  state.shown = state.presets.filter(matches);
  $("grid").replaceChildren(...state.shown.map(card));
  $("empty").hidden = state.shown.length > 0;
  $("count").textContent = `${state.shown.length} preset${state.shown.length === 1 ? "" : "s"}`;
  updateSelectionInfo();
}

function toggle(id) {
  if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id);
  const node = $("grid").querySelector(`[data-id="${CSS.escape(id)}"]`);
  if (node) setSelected(node, state.selected.has(id));
  updateSelectionInfo();
}

function updateSelectionInfo() {
  const n = state.selected.size;
  $("selected-info").textContent = n
    ? `${n} selected · ${minutes(n * state.secondsPerPreset)}`
    : "";
  $("apply-btn").disabled = n === 0;
}

// ---------- jobs ----------

async function startJob(promise) {
  const r = await promise;
  if (!r.ok) return showMessage("Can't start", r.error);
  setMini(true);
  watchJob();
}

// The page asks Python how the job is going a few times a second until it's finished.
async function watchJob() {
  for (;;) {
    const p = await api().get_progress();
    if (!p.running) {
      setMini(false);
      if (p.result) onDone(p.result);
      return;
    }
    onProgress(p);
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
}

function setMini(on) {
  document.body.classList.toggle("mini", on);
  $("full").hidden = on;
  $("mini").hidden = !on;
  if (on) {
    $("mini-title").textContent = "Starting…";
    $("mini-step").textContent = "";
    $("mini-bar").style.width = "0";
    $("mini-left").textContent = "";
  }
}

function onProgress(p) {
  $("mini-title").textContent = p.title;
  $("mini-step").textContent = p.step;
  $("mini-bar").style.width = `${Math.round(p.fraction * 100)}%`;
  $("mini-left").textContent = `${minutes(p.seconds_left)} left`;
}

async function onDone(r) {
  await load();
  if (r.report) return showReport(r);
  const title = r.stopped ? "Stopped" : r.error ? "Something went wrong" : r.title;
  const body = [el("p", { text: r.stopped || r.error || r.message || "Done." })];
  if (r.warning) body.push(el("p", { class: "warn-box", text: r.warning }));
  openModal(title, body, [button("OK", "primary", closeModal)]);
}

// ---------- modals ----------

function openModal(title, body, buttons) {
  $("modal-title").textContent = title;
  $("modal-body").replaceChildren(...body);
  $("modal-buttons").replaceChildren(...buttons);
  $("modal-bg").hidden = false;
  (buttons[buttons.length - 1] || {}).focus?.();
}

function closeModal() { $("modal-bg").hidden = true; }

function button(text, cls, onClick) {
  const b = el("button", { class: `btn ${cls}`, text });
  b.addEventListener("click", onClick);
  return b;
}

function showMessage(title, text) {
  openModal(title, [el("p", { text })], [button("OK", "primary", closeModal)]);
}

function showReport(r) {
  const list = el("ul", { class: "report" });
  const counts = { added: 0, already: 0, skipped: 0, error: 0 };
  for (const e of r.report) {
    counts[e.outcome] = (counts[e.outcome] || 0) + 1;
    const tagText = { added: "Added", already: "Already in your garage", skipped: "Skipped", error: "Problem" }[e.outcome] || "Not done";
    const li = el("li", {}, el("span", { class: "who", text: e.name }), el("span", { class: `tag ${e.outcome}`, text: tagText }));
    if (e.reason) li.append(el("div", { class: "swap", text: e.reason }));
    for (const s of e.swaps || []) {
      const team = s.team === "both" ? "" : ` (${s.team})`;
      const got = s.got ? `→ ${s.got}` : "→ left as it was";
      li.append(el("div", { class: "swap", text: `${SLOT_NAMES[s.slot] || s.slot}${team}: ${s.wanted} ${got}` }));
    }
    list.append(li);
  }
  const summary = [`${counts.added} added`];
  if (counts.already) summary.push(`${counts.already} already there`);
  if (counts.skipped) summary.push(`${counts.skipped} skipped`);
  if (counts.error) summary.push(`${counts.error} with problems`);
  const body = [el("p", { text: `${summary.join(" · ")} in ${minutes(r.seconds)}.` })];
  if (r.stopped) body.unshift(el("p", { class: "warn-box", text: `Stopped early: ${r.stopped}` }));
  if (r.error) body.unshift(el("p", { class: "warn-box", text: r.error }));
  if (r.warning) body.push(el("p", { class: "warn-box", text: r.warning }));
  body.push(list);
  openModal("Results", body, [button("Done", "primary", closeModal)]);
}

function confirmApply() {
  const n = state.selected.size;
  openModal(`Add ${n} preset${n === 1 ? "" : "s"}?`, [
    el("p", { text: `This takes ${minutes(n * state.secondsPerPreset)}. Each one goes into a new garage preset; your own presets aren't changed.` }),
    el("p", { text: "Keep your hands off the mouse and keyboard while it runs. Press Stop or F8 to stop." }),
  ], [
    button("Cancel", "", closeModal),
    button("Start", "primary", () => { closeModal(); startJob(api().start_apply([...state.selected], true)); }),
  ]);
}

function confirmClear() {
  const input = el("input", { type: "text", placeholder: "DELETE", "aria-label": "Type DELETE to confirm", spellcheck: "false" });
  const error = el("div", { class: "error-text" });
  input.addEventListener("input", () => { error.textContent = ""; });
  const go = button("Delete all presets", "danger", async () => {
    if (input.value.trim().toUpperCase() !== "DELETE") {
      error.textContent = "Type DELETE to confirm.";
      return;
    }
    closeModal();
    startJob(api().start_clear_all(input.value));
  });
  openModal("Clear all presets?", [
    el("div", { class: "warn-box", text: "This deletes every preset in your Rocket League garage, including ones you made yourself. It can't be undone. Type DELETE to confirm." }),
    input, error,
  ], [button("Cancel", "", closeModal), go]);
  input.focus();
}

// ---------- setup screens ----------

const setup = { step: 0, steps: 6, platform: null, resolution: null, custom: false, language: null, display: null, info: null };

function pretty(res) { return res.replace("x", " × "); }

async function openSetup() {
  const info = await api().get_setup();
  setup.info = info;
  setup.step = 0;
  // Pre-select what was detected (or saved before); the user still confirms with Next.
  setup.platform = info.platform || (info.saved || {}).platform || null;
  setup.resolution = info.resolution || (info.saved || {}).resolution || null;
  const lang = info.language ? (info.language === "english" ? "english" : "other") : null;
  setup.language = lang || (info.saved || {}).language || null;
  setup.display = info.display_mode || (info.saved || {}).display || null;
  markDetected("language-choices", lang);
  markDetected("display-choices", info.display_mode);

  for (const b of $("platform-choices").querySelectorAll(".choice")) {
    b.querySelector(".tag").hidden = b.dataset.value !== info.platform;
  }
  $("platform-hint").textContent = info.platform
    ? `Detected ${info.platform === "steam" ? "Steam" : "Epic Games"} from ${info.platform_from}. Change it if that's wrong.`
    : "Couldn't detect it, so pick one. Starting the game first lets the app detect it.";

  // The listed 16:9 sizes, then a Custom box for anything else (filled in when that's what was found).
  const detectedTag = () => el("span", { class: "tag", text: "Detected" });
  const choices = info.resolutions.map((r) => {
    const b = el("button", { class: "choice", "data-value": r }, el("span", { class: "choice-name", text: pretty(r) }));
    if (r === info.resolution) b.append(detectedTag());
    return b;
  });
  setup.custom = Boolean(setup.resolution) && !info.resolutions.includes(setup.resolution);
  const [w, h] = setup.custom ? setup.resolution.split("x") : ["", ""];
  const size = (id, label, value) => el("input", { type: "text", id, value, placeholder: label, inputmode: "numeric", maxlength: "5", "aria-label": label });
  choices.push(el("div", { class: "choice custom", "data-value": "custom" },
    size("custom-width", "Width", w), el("span", { text: "×" }), size("custom-height", "Height", h)));
  $("resolution-choices").replaceChildren(...choices);
  $("resolution-hint").textContent = info.resolution
    ? `Detected ${pretty(info.resolution)} from ${info.resolution_from}.`
    : "Couldn't detect it, so pick the one your game uses, or type it in the last box.";

  $("setup").hidden = false;
  showStep();
}

function isWide(res) {
  const [w, h] = res.split("x").map(Number);
  return Math.abs(w / h - 16 / 9) <= 0.02;
}

function readCustomSize() {
  const w = $("custom-width").value.trim(), h = $("custom-height").value.trim();
  const ok = /^\d{3,5}$/.test(w) && /^\d{3,5}$/.test(h);
  setup.resolution = ok ? `${w}x${h}` : null;
}

function markDetected(listId, value) {
  for (const b of $(listId).querySelectorAll(".choice")) b.querySelector(".tag").hidden = b.dataset.value !== value;
}

function showStep() {
  for (const s of document.querySelectorAll(".step")) s.hidden = Number(s.dataset.step) !== setup.step;
  $("setup-dots").replaceChildren(...Array.from({ length: setup.steps }, (_, i) => el("span", { class: i <= setup.step ? "on" : "" })));
  for (const b of $("platform-choices").querySelectorAll(".choice")) b.classList.toggle("selected", b.dataset.value === setup.platform);
  for (const b of $("resolution-choices").querySelectorAll(".choice")) {
    b.classList.toggle("selected", setup.custom ? b.dataset.value === "custom" : b.dataset.value === setup.resolution);
  }
  $("resolution-warn").hidden = !setup.resolution || isWide(setup.resolution);
  for (const b of $("language-choices").querySelectorAll(".choice")) b.classList.toggle("selected", b.dataset.value === setup.language);
  for (const b of $("display-choices").querySelectorAll(".choice")) b.classList.toggle("selected", b.dataset.value === setup.display);
  $("language-warn").hidden = setup.language !== "other";
  $("display-warn").hidden = setup.display !== "windowed";
  $("setup-back").hidden = setup.step === 0;
  const last = setup.step === setup.steps - 1;
  $("setup-later").hidden = !last;
  $("setup-next").textContent = setup.step === 0 ? "Get started" : last ? "Scan inventory now" : "Next";
  $("setup-next").disabled = (setup.step === 1 && !setup.platform) || (setup.step === 2 && !setup.resolution) ||
    (setup.step === 3 && !(setup.language && setup.display));
  if (last) {
    $("summary").textContent = `${setup.platform === "steam" ? "Steam" : "Epic Games"} · ${pretty(setup.resolution)}`;
  }
}

async function finishSetup(scan) {
  const r = await api().save_setup(setup.platform, setup.resolution, setup.language, setup.display);
  if (!r.ok) return showMessage("Setup", r.error);
  $("setup").hidden = true;
  $("launcher").value = setup.platform;
  await load();
  if (scan) startJob(api().start_scan());
}

function wireSetup() {
  $("platform-choices").addEventListener("click", (e) => {
    const b = e.target.closest(".choice");
    if (b) { setup.platform = b.dataset.value; showStep(); }
  });
  $("resolution-choices").addEventListener("click", (e) => {
    const b = e.target.closest(".choice");
    if (!b) return;
    setup.custom = b.dataset.value === "custom";
    if (setup.custom) {
      readCustomSize();
      if (e.target.tagName !== "INPUT") $("custom-width").focus();
    } else {
      setup.resolution = b.dataset.value;
    }
    showStep();
  });
  $("resolution-choices").addEventListener("input", (e) => {
    if (e.target.tagName !== "INPUT") return;
    e.target.value = e.target.value.replace(/\D/g, "");
    setup.custom = true;
    readCustomSize();
    showStep();
  });
  for (const [id, key] of [["language-choices", "language"], ["display-choices", "display"]]) {
    $(id).addEventListener("click", (e) => {
      const b = e.target.closest(".choice");
      if (b) { setup[key] = b.dataset.value; showStep(); }
    });
  }
  $("setup-back").addEventListener("click", () => { setup.step -= 1; showStep(); });
  $("setup-next").addEventListener("click", () => {
    if (setup.step === setup.steps - 1) return finishSetup(true);
    setup.step += 1;
    showStep();
  });
  $("setup-later").addEventListener("click", () => finishSetup(false));
  $("setup-btn").addEventListener("click", openSetup);
}

// ---------- wiring ----------

function wire() {
  $("grid").addEventListener("click", (e) => {
    const c = e.target.closest(".card");
    if (c) toggle(c.dataset.id);
  });
  $("grid").addEventListener("keydown", (e) => {
    const c = e.target.closest(".card");
    if (c && (e.key === " " || e.key === "Enter")) { e.preventDefault(); toggle(c.dataset.id); }
  });
  for (const [id] of FILTERS) $(id).addEventListener("change", render);
  for (const id of [...Object.values(STATUS_BOXES), "s-added"]) $(id).addEventListener("change", render);
  $("reset-filters").addEventListener("click", () => {
    for (const [id] of FILTERS) $(id).value = "";
    render();
  });
  $("select-all").addEventListener("click", () => {
    for (const p of state.shown) state.selected.add(p.id);
    render();
  });
  $("select-none").addEventListener("click", () => { state.selected.clear(); render(); });
  $("apply-btn").addEventListener("click", confirmApply);
  $("scan-btn").addEventListener("click", () => startJob(api().start_scan()));
  $("update-btn").addEventListener("click", startUpdate);
  $("clear-btn").addEventListener("click", confirmClear);
  $("launch-btn").addEventListener("click", async () => {
    await api().launch_game($("launcher").value);
    $("game-pill").textContent = "Starting the game…";
  });
  $("stop-btn").addEventListener("click", () => api().stop());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("modal-bg").hidden) closeModal();
  });
  // Keep the game status fresh while the window is idle.
  setInterval(async () => {
    if (document.body.classList.contains("mini")) return;
    showGame(await api().game_status());
  }, 5000);
}

// If start-up stalls, say so instead of leaving an empty window.
const startTimer = setTimeout(() => {
  $("loading-text").textContent = "This is taking longer than usual. If nothing shows up, close the app and open it again.";
}, 15000);

function reportError(message) {
  try { window.pywebview.api.log_error(String(message).slice(0, 500)); } catch (e) { /* not ready yet */ }
}
window.addEventListener("error", (e) => reportError(`${e.message} (${e.filename}:${e.lineno})`));
window.addEventListener("unhandledrejection", (e) => reportError(e.reason));

// ---------- updates ----------

async function checkUpdate() {
  const info = await api().check_update();
  if (!info) return;
  const b = $("update-btn");
  b.textContent = `Update to v${info.version}`;
  b.title = info.install ? "Downloads the new version from GitHub and restarts the app" : "Opens the download page";
  b.hidden = false;
}

async function startUpdate() {
  const b = $("update-btn");
  const r = await api().start_update();
  if (!r.ok) return showMessage("Can't update", r.error);
  if (r.opened) return;
  b.disabled = true;
  for (;;) {
    const p = await api().get_update_progress();
    if (p.state === "downloading") b.textContent = `Downloading ${Math.round(p.fraction * 100)}%`;
    else if (p.state === "restarting") { b.textContent = "Restarting…"; return; }
    else if (p.state === "error") {
      b.disabled = false;
      b.textContent = "Try update again";
      return showMessage("Update didn't work", p.error);
    }
    await new Promise((res) => setTimeout(res, 300));
  }
}

window.addEventListener("pywebviewready", async () => {
  wire();
  wireSetup();
  await load();
  clearTimeout(startTimer);
  $("loading").hidden = true;
  $("full").hidden = false;
  api().page_ready();
  checkUpdate();
  if (!(await api().get_setup()).saved) await openSetup();  // first run
  if ((await api().get_progress()).running) { setMini(true); watchJob(); }
});
