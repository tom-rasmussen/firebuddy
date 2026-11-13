// FireBuddy demo UI. Vanilla JS, no build step. All text is inserted with textContent.

const CHIP_QUESTIONS = ["Should I leave?", "Is the wind blowing my way?", "Where's the nearest shelter?", "What's the status?"];
const TEST_STEPS = [1, 2, 3, 4];
const CHOICES = [
  { id: "monitor", label: "Keep monitoring" },
  { id: "get_ready", label: "Get ready, and leave early if I need time" },
  { id: "leave", label: "Leave now" },
  { id: "shelter", label: "Shelter in place" },
];
const LEVEL_TO_CHOICE = {
  MONITOR: "monitor",
  "BE READY": "monitor",
  "GET READY: LEAVE EARLY IF YOU NEED TIME": "get_ready",
  "LEAVE NOW": "leave",
  "FOLLOW SHELTER ORDER": "shelter",
};

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
};

// ---------- API ----------
const stepCache = new Map();
async function api(path, init) {
  const res = await fetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}
async function getStep(n) {
  if (!stepCache.has(n)) stepCache.set(n, api(`/api/step/${n}`));
  return stepCache.get(n);
}
const askApi = (step, question) =>
  api("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ step, question }) });

function levelClass(level) {
  if (level.startsWith("BE READY")) return "level l-be";
  if (level.startsWith("GET READY")) return "level l-get";
  if (level.startsWith("LEAVE")) return "level l-leave";
  if (level.startsWith("FOLLOW SHELTER")) return "level l-shelter";
  return "level";
}

// ---------- shared chat helpers ----------
function addMsg(chat, kind, text, meta) {
  const m = el("div", { class: `msg ${kind}` }, meta ? el("span", { class: "meta", text: meta }) : null, text);
  chat.append(m);
  chat.scrollTop = chat.scrollHeight;
  return m;
}
function addDivider(chat, text) {
  chat.append(el("div", { class: "divider", text }));
}
function renderChips(container, onAsk) {
  container.replaceChildren(...CHIP_QUESTIONS.map((q) => el("button", { type: "button", text: q, onclick: () => onAsk(q) })));
}
function renderPushes(list, empty, steps, uptoIndex) {
  const items = [];
  steps.forEach((s, i) => {
    if (i <= uptoIndex && s.baseline) items.push({ s, isNew: i === uptoIndex });
  });
  list.replaceChildren(
    ...items.reverse().map(({ s, isNew }) =>
      el("li", { class: isNew ? "new" : "" }, el("span", { class: "meta", text: `County alert · ${s.clock}` }), s.baseline),
    ),
  );
  empty.hidden = items.length > 0;
}

// ---------- DEMO MODE ----------
async function startDemo() {
  $("demo").hidden = false;
  const scenario = await api("/api/scenario");
  const steps = await Promise.all(scenario.steps.map((s) => getStep(s.step)));
  let current = -1;
  let timer = null;
  const counts = { alerts: 0, questions: 0, levels: 0 };

  const stepButtons = steps.map((s, i) =>
    el("li", {}, el("button", { type: "button", onclick: () => goTo(i) }, el("b", { text: `${i}. ${s.clock}` }), s.title)),
  );
  $("steps").replaceChildren(...stepButtons);

  function log(ev, detail) {
    const clock = current >= 0 ? steps[current].clock : "";
    $("log").prepend(el("li", {}, el("span", { class: "ev", text: ev }), ` ${clock} · ${detail}`));
  }
  function setCounts() {
    $("c-alerts").textContent = counts.alerts;
    $("c-questions").textContent = counts.questions;
    $("c-levels").textContent = counts.levels;
  }

  function showStep(i, previousLevel) {
    const s = steps[i];
    addDivider($("chat"), `${s.clock} · ${s.title}`);
    for (const a of s.alerts) {
      addMsg($("chat"), "bot alert", a.text, "FireBuddy alert");
      counts.alerts++;
      log("alert_sent", a.kind);
    }
    if (previousLevel !== undefined && previousLevel !== s.assessment.level) {
      counts.levels++;
      log("level_changed", `${previousLevel} → ${s.assessment.level}`);
    }
  }

  function goTo(target) {
    stopPlay();
    if (target === current + 1) {
      const prev = current >= 0 ? steps[current].assessment.level : undefined;
      current = target;
      showStep(current, prev);
    } else {
      // Jumping or going back rebuilds the chat from the start.
      $("chat").replaceChildren();
      $("log").replaceChildren();
      Object.assign(counts, { alerts: 0, questions: 0, levels: 0 });
      let prev;
      for (let i = 0; i <= target; i++) {
        current = i;
        showStep(i, prev);
        prev = steps[i].assessment.level;
      }
      current = target;
      $("trace").replaceChildren(el("p", { class: "empty", text: "Ask a question to see the decision trace." }));
    }
    render();
  }

  function render() {
    const s = steps[current];
    $("step-title").textContent = s.title;
    $("step-clock").textContent = s.clock;
    stepButtons.forEach((li, i) => {
      li.firstChild.className = i === current ? "current" : i < current ? "past" : "";
    });
    $("level-badge").textContent = s.assessment.level;
    $("level-badge").className = levelClass(s.assessment.level);
    renderPushes($("pushes"), $("pushes-empty"), steps, current);
    $("prev").disabled = current === 0;
    $("next").disabled = current === steps.length - 1;
    setCounts();
  }

  function renderTrace(q, res) {
    const t = res.trace;
    const decided = el("span", { class: `pill ${t.decidedBy}`, text: t.decidedBy === "rules" ? "Rules" : "Template" });
    $("trace").replaceChildren(
      el(
        "dl",
        {},
        el("dt", { text: "Question" }), el("dd", { text: q }),
        el("dt", { text: "Intent" }), el("dd", { text: t.intent }),
        el("dt", { text: "Decided by" }), el("dd", {}, decided, ...t.components.map((c) => el("span", { class: "pill", text: c }))),
        el("dt", { text: "Level" }), el("dd", {}, el("span", { class: levelClass(t.level), text: t.level })),
        el("dt", { text: "Escalated" }), el("dd", { text: t.escalated ? "Yes, user reported flames (rules can raise, never lower)" : "No" }),
        el("dt", { text: "Safety check" }), el("dd", {}, el("span", { class: `pill ${t.validator === "pass" ? "rules" : "warn"}`, text: t.validator === "pass" ? "Passed: no safety claims or routes" : "Failed: fell back to status" })),
        el("dt", { text: "LLM used" }), el("dd", { text: "No" }),
        el("dt", { text: "Sources" }), el("dd", { text: t.sources.join(", ") }),
      ),
    );
  }

  async function onAsk(q) {
    const question = q.trim();
    if (!question) return;
    addMsg($("chat"), "user", question);
    counts.questions++;
    try {
      const res = await askApi(current, question);
      addMsg($("chat"), "bot", res.reply);
      log("question_asked", res.trace.intent);
      renderTrace(question, res);
    } catch (e) {
      addMsg($("chat"), "bot", e.message);
    }
    setCounts();
  }

  function stopPlay() {
    if (timer) clearInterval(timer);
    timer = null;
    $("play").textContent = "▶ Play";
  }
  $("play").addEventListener("click", () => {
    if (timer) return stopPlay();
    if (current === steps.length - 1) goTo(0);
    $("play").textContent = "❚❚ Pause";
    timer = setInterval(() => {
      if (current >= steps.length - 1) return stopPlay();
      const prev = steps[current].assessment.level;
      current++;
      showStep(current, prev);
      render();
    }, 5000);
  });
  $("next").addEventListener("click", () => goTo(current + 1));
  $("prev").addEventListener("click", () => goTo(current - 1));
  $("reset").addEventListener("click", () => goTo(0));
  $("ask-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("ask-input").value;
    $("ask-input").value = "";
    onAsk(q);
  });
  renderChips($("chips"), onAsk);
  goTo(0);
}

// ---------- TEST MODE ----------
async function startTest(condition) {
  $("test").hidden = false;
  const label = condition === "baseline" ? "Condition A: county alerts only" : "Condition B: FireBuddy";
  $("test-condition").textContent = label;
  const scenario = await api("/api/scenario");
  const steps = await Promise.all(scenario.steps.map((s) => getStep(s.step)));
  const results = [];
  let idx = 0;
  let startedAt = 0;
  let questions = 0;

  $("test-baseline").hidden = condition !== "baseline";
  $("test-firebuddy").hidden = condition !== "firebuddy";
  $("choices").replaceChildren(
    ...CHOICES.map((c) => el("button", { type: "button", text: c.label, onclick: () => decide(c.id) })),
  );

  async function onAsk(q) {
    const question = q.trim();
    if (!question) return;
    questions++;
    addMsg($("test-chat"), "user", question);
    try {
      const res = await askApi(TEST_STEPS[idx], question);
      addMsg($("test-chat"), "bot", res.reply);
    } catch (e) {
      addMsg($("test-chat"), "bot", e.message);
    }
  }
  renderChips($("test-chips"), onAsk);
  $("test-ask-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("test-ask-input").value;
    $("test-ask-input").value = "";
    onAsk(q);
  });

  function showMoment() {
    const n = TEST_STEPS[idx];
    const s = steps[n];
    // Neutral titles in test mode, so the title doesn't give away the answer.
    $("test-progress").textContent = `${label} · Moment ${idx + 1} of ${TEST_STEPS.length}`;
    $("test-title").textContent = `Moment ${idx + 1}`;
    $("test-clock").textContent = s.clock;
    if (condition === "baseline") {
      renderPushes($("test-pushes"), $("test-pushes-empty"), steps, n);
    } else {
      // Show every FireBuddy alert that would have arrived since the scenario started.
      const from = idx === 0 ? 0 : TEST_STEPS[idx - 1] + 1;
      addDivider($("test-chat"), `${s.clock}`);
      for (let i = from; i <= n; i++) for (const a of steps[i].alerts) addMsg($("test-chat"), "bot alert", a.text, "FireBuddy alert");
    }
    questions = 0;
    window.scrollTo({ top: 0 });
    startedAt = performance.now();
  }

  function decide(choice) {
    const n = TEST_STEPS[idx];
    const level = steps[n].assessment.level;
    const expected = LEVEL_TO_CHOICE[level];
    results.push({
      moment: idx + 1,
      step: n,
      choice,
      expected,
      correct: choice === expected,
      correctLevel: level,
      seconds: Math.round((performance.now() - startedAt) / 100) / 10,
      questions,
    });
    idx++;
    if (idx < TEST_STEPS.length) showMoment();
    else finish();
  }

  function median(xs) {
    if (!xs.length) return null;
    const a = [...xs].sort((x, y) => x - y);
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : Math.round(((a[m - 1] + a[m]) / 2) * 10) / 10;
  }

  function finish() {
    $("test-run").hidden = true;
    $("test-results").hidden = false;
    const correct = results.filter((r) => r.correct);
    const med = median(results.map((r) => r.seconds));
    const medCorrect = median(correct.map((r) => r.seconds));
    $("results-summary").textContent =
      `${label}: ${correct.length} of ${results.length} decisions matched the correct level. ` +
      `Median time per decision: ${med} s` +
      (medCorrect != null ? `; on correct decisions: ${medCorrect} s.` : ".");
    const name = (id) => CHOICES.find((c) => c.id === id).label;
    $("results-body").replaceChildren(
      ...results.map((r) =>
        el(
          "tr",
          {},
          el("td", { text: String(r.moment) }),
          el("td", { class: r.correct ? "ok" : "bad", text: name(r.choice) }),
          el("td", { text: r.correctLevel }),
          el("td", { text: String(r.seconds) }),
          el("td", { text: String(r.questions) }),
        ),
      ),
    );
    const payload = {
      participant: $("pid").value.trim() || null,
      condition,
      finishedAt: new Date().toISOString(),
      correct: correct.length,
      total: results.length,
      medianSeconds: med,
      medianSecondsCorrect: medCorrect,
      decisions: results,
    };
    $("copy-results").onclick = async () => {
      const text = JSON.stringify(payload, null, 2);
      try {
        await navigator.clipboard.writeText(text);
        $("copy-results").textContent = "Copied ✓";
      } catch {
        const ta = el("textarea", { rows: "10", style: "width:100%" });
        ta.value = text;
        $("copy-results").after(ta);
        ta.select();
      }
    };
    const other = condition === "baseline" ? "firebuddy" : "baseline";
    $("other-condition").href = `/?mode=${other}`;
    $("other-condition").textContent = other === "firebuddy" ? "Next: run Condition B (FireBuddy)" : "Run Condition A (baseline)";
  }

  $("test-start").addEventListener("click", () => {
    $("test-intro").hidden = true;
    $("test-run").hidden = false;
    showMoment();
  });
}

// ---------- boot ----------
const mode = new URLSearchParams(location.search).get("mode");
for (const a of document.querySelectorAll(".modes a[data-mode]")) {
  if (a.dataset.mode === (mode === "baseline" || mode === "firebuddy" ? mode : "demo")) a.classList.add("active");
}
(mode === "baseline" || mode === "firebuddy" ? startTest(mode) : startDemo()).catch((e) => {
  document.querySelector("main:not([hidden])")?.prepend(el("p", { class: "empty", text: `Couldn't load the demo: ${e.message}` }));
});
