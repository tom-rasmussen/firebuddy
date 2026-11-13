// FireBuddy web demo: static UI from public/, JSON API under /api/*.

import { answer } from "./engine/answer";
import { alertsAt, assessState, windForState } from "./engine/monitor";
import { formatTime } from "./engine/templates";
import { PLACE, RADIUS_MI, STEP_COUNT, TZ, stateAt } from "./scenario/morgan";

const MAX_QUESTION_CHARS = 200;

function json(data: unknown, status = 200): Response {
  return Response.json(data, { status, headers: { "cache-control": "no-store" } });
}

function parseStep(raw: unknown): number | null {
  const n = typeof raw === "string" ? Number(raw) : raw;
  return typeof n === "number" && Number.isInteger(n) && n >= 0 && n < STEP_COUNT ? n : null;
}

function stepPayload(n: number) {
  const state = stateAt(n);
  const assessment = assessState(state);
  const wind = windForState(state);
  return {
    step: n,
    title: state.title,
    clock: formatTime(state.clock, TZ),
    clockIso: state.clock,
    baseline: state.baseline,
    alerts: alertsAt(n),
    assessment,
    // Inputs for the situation map: positions relative to Home, all simulated.
    map: {
      radiusMi: RADIUS_MI,
      fires: state.fires.map((f) => ({
        name: f.name,
        distanceMi: f.distance_mi,
        bearingDeg: f.bearing_deg,
        direction: f.direction,
        acres: f.acres,
        contained: f.percent_contained,
      })),
      wind: {
        fromDeg: wind.wind_from_deg ?? null,
        mph: wind.wind_speed_mph ?? null,
        gustMph: wind.wind_gust_mph ?? null,
        relation: wind.relation_to_fire ?? null,
      },
      shelters: state.shelters.map((s) => ({ name: s.name, distanceMi: s.distance_mi })),
    },
    simulated: true,
  };
}

export default {
  async fetch(request, env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path.startsWith("/api/")) {
      // AC-15: per-IP rate limit on the API.
      const ip = request.headers.get("cf-connecting-ip") ?? "local";
      const { success } = await env.RATE_LIMITER.limit({ key: ip });
      if (!success) {
        return json({ error: "Too many requests. Please wait a minute and try again." }, 429);
      }
    }

    if (path === "/api/health") return json({ ok: true });

    if (path === "/api/scenario" && request.method === "GET") {
      return json({
        place: { label: PLACE.label, address: PLACE.address, radiusMi: RADIUS_MI },
        steps: Array.from({ length: STEP_COUNT }, (_, n) => {
          const s = stateAt(n);
          return { step: n, title: s.title, clock: formatTime(s.clock, TZ) };
        }),
        disclaimer: "Independent concept, not affiliated with Watch Duty. All fire data in this demo is simulated.",
      });
    }

    const stepMatch = path.match(/^\/api\/step\/([^/]+)$/);
    if (stepMatch && request.method === "GET") {
      const n = parseStep(stepMatch[1]);
      if (n === null) return json({ error: `step must be an integer from 0 to ${STEP_COUNT - 1}` }, 400);
      return json(stepPayload(n));
    }

    if (path === "/api/ask" && request.method === "POST") {
      let body: unknown;
      try {
        body = await request.json();
      } catch {
        return json({ error: "Body must be JSON: { step, question }" }, 400);
      }
      const { step, question } = (body ?? {}) as { step?: unknown; question?: unknown };
      const n = parseStep(step);
      if (n === null) return json({ error: `step must be an integer from 0 to ${STEP_COUNT - 1}` }, 400);
      if (typeof question !== "string" || question.trim() === "") return json({ error: "question is required" }, 400);
      const q = question.trim().slice(0, MAX_QUESTION_CHARS);
      return json({ step: n, question: q, ...answer(stateAt(n), q) });
    }

    if (path.startsWith("/api/")) return json({ error: "Not found" }, 404);
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
