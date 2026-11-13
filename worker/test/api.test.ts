import { exports } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { LEVEL_LEAVE_NOW, LEVEL_ORDER } from "../src/engine/assess";
import { BLOCKED_PHRASES, answer, classify } from "../src/engine/answer";
import { assessState } from "../src/engine/monitor";
import { FEEL_UNSAFE_LINE } from "../src/engine/templates";
import { STEP_COUNT, stateAt } from "../src/scenario/morgan";

let ipCounter = 0;
const call = (path: string, init?: RequestInit, ip = `10.0.0.${++ipCounter}`) =>
  exports.default.fetch(`https://example.com${path}`, {
    ...init,
    headers: { "cf-connecting-ip": ip, "content-type": "application/json", ...(init?.headers ?? {}) },
  });
const ask = (step: unknown, question: unknown, ip?: string) =>
  call("/api/ask", { method: "POST", body: JSON.stringify({ step, question }) }, ip);

const QUESTIONS = [
  "Should I leave?",
  "Am I safe?",
  "is it safe to stay",
  "Is the wind blowing my way?",
  "Where's the nearest shelter?",
  "What route should I take?",
  "I can see flames",
  "What's the status?",
  "hello",
];

describe("intent router", () => {
  it.each([
    ["Should I leave?", "readiness"],
    ["am i safe", "readiness"],
    ["Is the wind blowing my way?", "wind"],
    ["where should I go", "shelter"],
    ["find an evacuation center", "shelter"],
    ["what route should I take", "route"],
    ["I can see flames from my yard", "flames"],
    ["what's the latest", "status"],
    ["hi", "help"],
  ])("classifies %j as %s", (q, intent) => {
    expect(classify(q)).toBe(intent);
  });
});

describe("answers", () => {
  it("AC-6: 'should I leave?' gives the level, the facts behind it, and ends with the 911 line", () => {
    for (let n = 0; n < STEP_COUNT; n++) {
      const s = stateAt(n);
      const { reply, trace } = answer(s, "Should I leave?");
      const level = assessState(s).level;
      expect(reply.startsWith(level)).toBe(true);
      expect(trace.level).toBe(level);
      expect(reply.trimEnd().endsWith(FEEL_UNSAFE_LINE)).toBe(true);
      for (const fact of assessState(s).facts) expect(reply).toContain(fact);
    }
  });

  it("AC-5: during the evacuation order the answer is LEAVE NOW and quotes the order", () => {
    const s = stateAt(4);
    const { reply } = answer(s, "should I leave");
    expect(reply.startsWith(LEVEL_LEAVE_NOW)).toBe(true);
    const order = s.alerts.find((a) => a.event === "Evacuation Immediate")!;
    expect(reply).toContain(`"${order.instruction}"`);
  });

  it("AC-7: the wind answer gives the relation, source and time, and the terrain caveat", () => {
    const { reply } = answer(stateAt(2), "is the wind blowing my way?");
    expect(reply).toContain("blowing from Morgan Fire toward you");
    expect(reply).toContain("simulated KCCR obs, 4:30 PM PDT");
    expect(reply).toContain("embers can travel miles ahead");
  });

  it("AC-8: shelters are listed with distance, pets and access, or the no-shelter fallback", () => {
    const open = answer(stateAt(5), "where's the nearest shelter?").reply;
    expect(open).toMatch(/Monte Vista HS Gym, .*~1\.3 mi\. Pets: yes\. Accessible: yes\./);
    expect(open).toContain("Confirm with your county");
    const none = answer(stateAt(2), "where's the nearest shelter?").reply;
    expect(none).toContain("No open shelters listed near you right now.");
    expect(none).toContain("211");
  });

  it("AC-9: no reply ever contains a safety claim or a generated route", () => {
    for (let n = 0; n < STEP_COUNT; n++) {
      for (const q of QUESTIONS) {
        const { reply, trace } = answer(stateAt(n), q);
        for (const re of BLOCKED_PHRASES) expect(reply).not.toMatch(re);
        expect(trace.validator).toBe("pass");
      }
    }
  });

  it("AC-9: a user report of flames can raise the level but nothing ever lowers it", () => {
    for (let n = 0; n < STEP_COUNT; n++) {
      const s = stateAt(n);
      const base = assessState(s).level;
      for (const q of QUESTIONS) {
        const { trace } = answer(s, q);
        expect(LEVEL_ORDER.indexOf(trace.level)).toBeGreaterThanOrEqual(LEVEL_ORDER.indexOf(base));
      }
      expect(answer(s, "I can see flames").trace.level).toBe(LEVEL_LEAVE_NOW);
    }
  });

  it("AC-11: every reply says what decided it", () => {
    for (const q of QUESTIONS) {
      const { trace } = answer(stateAt(3), q);
      expect(["rules", "template"]).toContain(trace.decidedBy);
      expect(trace.components.length).toBeGreaterThan(0);
      expect(trace.sources.every((s) => s.startsWith("simulated"))).toBe(true);
    }
  });
});

describe("API", () => {
  it("GET /api/scenario lists the steps and the disclaimer", async () => {
    const res = await call("/api/scenario");
    expect(res.status).toBe(200);
    const body = (await res.json()) as any;
    expect(body.steps).toHaveLength(STEP_COUNT);
    expect(body.disclaimer).toContain("not affiliated with Watch Duty");
  });

  it("GET /api/step/:n returns baseline, alerts and assessment", async () => {
    const res = await call("/api/step/4");
    expect(res.status).toBe(200);
    const body = (await res.json()) as any;
    expect(body.baseline).toContain("Check your zone");
    expect(body.alerts[0].kind).toBe("official");
    expect(body.assessment.level).toBe(LEVEL_LEAVE_NOW);
    expect(body.simulated).toBe(true);
    expect(body.map.fires[0]).toMatchObject({ name: "Morgan Fire", direction: "E" });
    expect(body.map.wind.relation).toBe("toward");
  });

  it.each(["7", "-1", "1.5", "abc"])("GET /api/step/%s is rejected", async (n) => {
    expect((await call(`/api/step/${n}`)).status).toBe(400);
  });

  it("POST /api/ask answers and validates input", async () => {
    const ok = await ask(2, "Should I leave?");
    expect(ok.status).toBe(200);
    const body = (await ok.json()) as any;
    expect(body.trace.intent).toBe("readiness");
    expect((await ask(99, "x")).status).toBe(400);
    expect((await ask(1, "   ")).status).toBe(400);
    const bad = await call("/api/ask", { method: "POST", body: "not json" });
    expect(bad.status).toBe(400);
  });

  it("POST /api/ask trims long questions to 200 characters", async () => {
    const res = await ask(1, `should I leave ${"x".repeat(500)}`);
    const body = (await res.json()) as any;
    expect(body.question.length).toBe(200);
  });

  it("unknown API routes are 404 and the UI is served from static assets", async () => {
    expect((await call("/api/nope")).status).toBe(404);
    const page = await call("/");
    expect(page.status).toBe(200);
    expect(await page.text()).toContain("not affiliated with Watch Duty");
  });

  it("AC-15: over 120 requests a minute from one IP returns a friendly 429", async () => {
    const ip = "203.0.113.7";
    const statuses: number[] = [];
    for (let i = 0; i < 125; i++) statuses.push((await call("/api/health", undefined, ip)).status);
    expect(statuses.slice(0, 120).every((s) => s === 200)).toBe(true);
    const limited = await call("/api/health", undefined, ip);
    expect(limited.status).toBe(429);
    expect(((await limited.json()) as any).error).toContain("wait a minute");
  });
});
