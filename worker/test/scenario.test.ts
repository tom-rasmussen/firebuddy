import { describe, expect, it } from "vitest";
import { LEVEL_BE_READY, LEVEL_GET_READY, LEVEL_LEAVE_NOW, LEVEL_MONITOR } from "../src/engine/assess";
import { alertsAt, assessState } from "../src/engine/monitor";
import { STEP_COUNT, stateAt } from "../src/scenario/morgan";

const EXPECTED_LEVELS = [
  LEVEL_MONITOR, // quiet
  LEVEL_BE_READY, // fire 9 mi E, wind away
  LEVEL_GET_READY, // wind toward + Red Flag
  LEVEL_GET_READY, // growth
  LEVEL_LEAVE_NOW, // evacuation order
  LEVEL_LEAVE_NOW, // order still in effect
  LEVEL_BE_READY, // contained, order lifted, fire still listed
];

const allAlerts = () => Array.from({ length: STEP_COUNT }, (_, n) => alertsAt(n));

describe("replay scenario", () => {
  it("has 7 steps", () => {
    expect(STEP_COUNT).toBe(7);
  });

  it.each(EXPECTED_LEVELS.map((level, n) => [n, level] as const))("AC-4: step %i readiness level is %s", (n, level) => {
    expect(assessState(stateAt(n)).level).toBe(level);
  });

  it("AC-1: a new fire produces exactly one alert, with distance, direction, size, containment, source and time", () => {
    const newFire = allAlerts().flat().filter((a) => a.kind === "new_fire");
    expect(newFire).toHaveLength(1);
    expect(alertsAt(1).map((a) => a.kind)).toContain("new_fire");
    const text = newFire[0]!.text;
    for (const part of ["~9 mi E", "40 acres", "0% contained", "simulated NIFC", "3:58 PM PDT"]) expect(text).toContain(part);
  });

  it("AC-2: one alert per growth threshold, one containment alert, nothing repeats", () => {
    const flat = allAlerts().flat();
    expect(flat.filter((a) => a.kind === "growth").map((a) => a.key)).toEqual([
      "growth:SIM-MORGAN:100",
      "growth:SIM-MORGAN:1000",
    ]);
    expect(flat.filter((a) => a.kind === "containment")).toHaveLength(1);
    expect(alertsAt(6).map((a) => a.kind)).toEqual(["containment"]);
    const keys = flat.map((a) => a.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("AC-2: steps where nothing new happens send nothing", () => {
    expect(alertsAt(0)).toEqual([]);
  });

  it("AC-3: official alerts are quoted word for word with sender and sent time", () => {
    const evac = alertsAt(4).find((a) => a.kind === "official");
    const order = stateAt(4).alerts.find((a) => a.event === "Evacuation Immediate")!;
    expect(evac?.text).toContain(order.headline!);
    expect(evac?.text).toContain(order.instruction!);
    expect(evac?.text).toContain(`(${order.sender_name}, sent 6:10 PM PDT)`);
    // The Red Flag Warning alerts once, at step 2, even though it stays in effect.
    expect(allAlerts().flat().filter((a) => a.key === "nws:sim-redflag-1")).toHaveLength(1);
  });

  it("AC-10: every fire, alert, wind reading and shelter is labelled simulated", () => {
    for (let n = 0; n < STEP_COUNT; n++) {
      const s = stateAt(n);
      for (const f of s.fires) expect(f.source).toMatch(/simulated/);
      for (const a of s.alerts) {
        expect(a.headline).toMatch(/simulated/);
        expect(a.sender_name).toMatch(/simulated/);
      }
      expect(s.wind.station_id).toMatch(/simulated/);
      for (const sh of s.shelters) expect(sh.org).toMatch(/simulated/);
    }
  });

  it("wind forecasts are always in the future relative to the observation", () => {
    for (let n = 0; n < STEP_COUNT; n++) {
      const s = stateAt(n);
      for (const p of s.wind.forecast_hourly ?? []) {
        expect(Date.parse(p.start_time!)).toBeGreaterThan(Date.parse(s.wind.obs_time!));
      }
    }
  });
});
