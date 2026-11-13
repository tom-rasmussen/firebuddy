// Deterministic answers to the core questions (no LLM in this demo).
// Every reply passes the same blocked-phrase check as the Python validator (AC-9).

import { LEVEL_LEAVE_NOW, LEVEL_ORDER, LEVEL_SHELTER } from "./assess";
import { assessState, windForState } from "./monitor";
import { FEEL_UNSAFE_LINE, fireLine, formatTime, statusUpdate, windLine } from "./templates";
import type { Fire, OfficialAlert } from "./types";
import { PLACE, TZ, type WorldState } from "../scenario/morgan";

export type Intent = "readiness" | "wind" | "shelter" | "status" | "route" | "flames" | "help";

export interface Trace {
  intent: Intent;
  decidedBy: "rules" | "template";
  components: string[];
  level: string;
  escalated: boolean;
  sources: string[];
  validator: "pass" | "fallback";
}

export interface Answer {
  reply: string;
  trace: Trace;
}

export const ZONE_LOOKUP = "Check your zone: protect.genasys.com/search";

/** Same patterns as BLOCKED_PHRASES in firebuddy/agent.py. */
export const BLOCKED_PHRASES = [
  /you'?re safe/i,
  /it'?s safe/i,
  /no need to leave/i,
  /you can stay/i,
  /take\s+(I-|Hwy|Highway|Route|SR|US)\s?\d+/i,
];

/** Order matters: more specific intents first. */
export function classify(question: string): Intent {
  const q = question.toLowerCase();
  if (/\b(flames?|on fire|see (the )?fire|fire is here|embers? (on|in))\b/.test(q)) return "flames";
  if (/\b(route|which way|what road|how do i get out|drive|highway)\b/.test(q)) return "route";
  if (/\b(shelter|evacuation (center|centre|point)|where (do|should|can) i go|where to go)\b/.test(q)) return "shelter";
  if (/\bwind\b|\bblowing\b/.test(q)) return "wind";
  if (/\b(leave|evacuate|go now|stay|safe|danger|should i|do i need|what do i do|ready)\b/.test(q)) return "readiness";
  if (/\b(status|update|what'?s happening|latest|news|fire near)\b/.test(q)) return "status";
  return "help";
}

const SOURCES = ["simulated NIFC fire feed", "simulated NWS alerts", "simulated NWS wind obs"];

function nearest(fires: Fire[]): Fire | null {
  return fires.reduce<Fire | null>((best, f) => (best === null || f.distance_mi < best.distance_mi ? f : best), null);
}

function quoteOrder(a: OfficialAlert): string {
  const words = a.instruction || a.description || a.headline || "";
  return `${a.event} (${a.sender_name ?? "official source"}, sent ${formatTime(a.sent, TZ)}): "${words}"`;
}

function moreUrgent(a: string, b: string): string {
  return LEVEL_ORDER.indexOf(a) >= LEVEL_ORDER.indexOf(b) ? a : b;
}

function readinessReply(state: WorldState, opts: { escalateTo?: string; preface?: string } = {}) {
  const assessment = assessState(state);
  const level = opts.escalateTo ? moreUrgent(opts.escalateTo, assessment.level) : assessment.level;
  const escalated = level !== assessment.level;
  const lines: string[] = [];
  if (opts.preface) lines.push(opts.preface);
  if (escalated) {
    lines.push(`${level}. If you can see flames near you, leave now and call 911.`);
  } else {
    lines.push(`${level}. ${assessment.guidance}`);
  }
  if (assessment.facts.length) {
    lines.push("Why:");
    for (const f of assessment.facts) lines.push(`- ${f}`);
  }
  const fire = nearest(state.fires);
  if (fire) lines.push(`- ${fireLine(fire, TZ)}`);
  lines.push(`- ${windLine(windForState(state), TZ)}`);
  const orders = state.alerts.filter((a) => a.event === "Evacuation Immediate" || a.event === "Fire Warning" || a.event === "Shelter In Place Warning");
  for (const a of orders) lines.push(`Official order, word for word: ${quoteOrder(a)}`);
  if (level !== LEVEL_SHELTER && (fire || orders.length)) lines.push(ZONE_LOOKUP);
  lines.push(FEEL_UNSAFE_LINE);
  return { text: lines.join("\n"), level, escalated };
}

function windReply(state: WorldState): string {
  const wind = windForState(state);
  const lines = [windLine(wind, TZ)];
  const next = (wind.forecast_hourly ?? []).find((p) => p.wind_speed);
  if (next) lines.push(`Forecast: ${next.wind_direction ?? ""} ${next.wind_speed} from ${formatTime(next.start_time, TZ)}.`.replace("  ", " "));
  lines.push("Local and terrain winds can differ, and embers can travel miles ahead of a fire.");
  return lines.join("\n");
}

function shelterReply(state: WorldState): string {
  if (state.shelters.length === 0) {
    return [
      "No open shelters listed near you right now.",
      "Check your county's office of emergency services or call 211.",
      "If an official order names an evacuation point, use that one.",
    ].join("\n");
  }
  const lines = ["Open shelters nearest Home (simulated FEMA shelter list):"];
  state.shelters.forEach((s, i) => {
    const pets = s.pets === "Y" ? "Pets: yes" : "Pets: no";
    const ada = s.ada === "Y" ? "Accessible: yes" : "Accessible: unknown";
    lines.push(`${i + 1}. ${s.name}, ${s.address}, ~${s.distance_mi} mi. ${pets}. ${ada}.`);
  });
  lines.push("Shelter status changes fast. Confirm with your county before driving. If an official order names a different evacuation point, use that one.");
  return lines.join("\n");
}

function routeReply(state: WorldState): string {
  const lines = ["I don't generate evacuation routes. Follow the routes named by law enforcement and officials."];
  const order = state.alerts.find((a) => a.event === "Evacuation Immediate" || a.event === "Fire Warning");
  if (order) lines.push(`Official order, word for word: ${quoteOrder(order)}`);
  lines.push(ZONE_LOOKUP);
  lines.push(FEEL_UNSAFE_LINE);
  return lines.join("\n");
}

const HELP =
  'I can answer: "Should I leave?", "Is the wind blowing my way?", "Where\'s the nearest shelter?", or "What\'s the status?"';

/** Blocked phrases are allowed only when quoted word for word from an official alert. */
export function validate(reply: string, state: WorldState): boolean {
  const official = state.alerts.map((a) => [a.headline, a.description, a.instruction].join(" ")).join(" ");
  return BLOCKED_PHRASES.every((re) => {
    const m = reply.match(re);
    return !m || official.toLowerCase().includes(m[0].toLowerCase());
  });
}

export function answer(state: WorldState, question: string): Answer {
  const intent = classify(question);
  const base = assessState(state);
  let reply: string;
  let level = base.level;
  let escalated = false;
  let decidedBy: Trace["decidedBy"] = "template";
  let components: string[] = ["templates"];

  switch (intent) {
    case "readiness": {
      const asksSafe = /\bsafe\b/i.test(question);
      const r = readinessReply(state, asksSafe ? { preface: "I can't promise safety. Here's what I can see." } : {});
      reply = r.text;
      decidedBy = "rules";
      components = ["readiness rules (assess)", "wind math", "templates"];
      break;
    }
    case "flames": {
      const r = readinessReply(state, { escalateTo: LEVEL_LEAVE_NOW });
      reply = r.text;
      level = r.level;
      escalated = r.escalated;
      decidedBy = "rules";
      components = ["readiness rules (assess)", "escalation rule: user reports flames", "templates"];
      break;
    }
    case "wind":
      reply = windReply(state);
      components = ["wind math", "templates"];
      break;
    case "shelter":
      reply = shelterReply(state);
      break;
    case "route":
      reply = routeReply(state);
      components = ["no-generated-routes rule", "templates"];
      break;
    case "status":
      reply = statusUpdate(PLACE.label, state.fires, state.alerts, windForState(state), TZ);
      break;
    default:
      reply = HELP;
  }

  let validator: Trace["validator"] = "pass";
  if (!validate(reply, state)) {
    validator = "fallback";
    reply = `I couldn't verify a full answer. Here's what I know for sure.\n${statusUpdate(PLACE.label, state.fires, state.alerts, windForState(state), TZ)}`;
  }
  return { reply, trace: { intent, decidedBy, components, level, escalated, sources: SOURCES, validator } };
}
