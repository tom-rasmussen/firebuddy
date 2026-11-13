// Constitution quality gate 2: the TypeScript engine must match the Python engine exactly.
// golden.json is produced by `npm run golden` (scripts/export_golden.py).

import { describe, expect, it } from "vitest";
import golden from "./golden.json";
import * as assess from "../src/engine/assess";
import * as geo from "../src/engine/geo";
import { pyRound } from "../src/engine/pyfmt";
import * as t from "../src/engine/templates";
import type { Fire, OfficialAlert, WindData, WindRelation } from "../src/engine/types";

const g = golden as any;
const tz = g.templates.tz as string;

describe("geo parity", () => {
  it.each(g.geo.pairs as any[])("distance, bearing and compass to %j", (c) => {
    const [lat1, lon1] = c.from;
    const [lat2, lon2] = c.to;
    const d = geo.haversineMi(lat1, lon1, lat2, lon2);
    const b = geo.bearingDeg(lat1, lon1, lat2, lon2);
    expect(d).toBeCloseTo(c.distance_mi, 9);
    expect(pyRound(d, 1)).toBe(c.distance_mi_r1);
    expect(b).toBeCloseTo(c.bearing_deg, 9);
    expect(pyRound(b, 1)).toBe(c.bearing_deg_r1);
    expect(geo.compass16(b)).toBe(c.compass);
  });

  it("compass labels", () => {
    for (const [d, label] of Object.entries(g.geo.compass)) expect(geo.compass16(Number(d))).toBe(label);
  });

  it("angular difference", () => {
    for (const [a, b, want] of g.geo.angular_diff) expect(geo.angularDiff(a, b)).toBe(want);
  });

  it("Python rounding (ties to even, exact binary value)", () => {
    for (const [x, nd, want] of g.geo.round) expect(pyRound(x, nd)).toBe(want);
  });
});

describe("assess parity", () => {
  const now = new Date(g.assess.now);

  it("AC-7: wind relation toward / crosswind / away / light", () => {
    for (const [w, s, b, want] of g.assess.wind_relation) expect(assess.windRelation(w, s, b)).toBe(want);
  });

  it("AC-7: readings older than 2 hours are stale", () => {
    for (const [time, want] of g.assess.stale) expect(assess.windIsStale(time, now)).toBe(want);
  });

  it("AC-7: wind check shape, relation and caveat", () => {
    for (const c of g.assess.wind_check) {
      expect(assess.windCheck(c.wind as WindData, c.bearing, now)).toEqual(c.output);
    }
  });

  it.each(Object.entries(g.assess.situations) as [string, any][])("AC-4: readiness level matches Python for %s", (_name, c) => {
    const out = assess.assessSituation(
      c.input.fires as Fire[],
      c.input.alerts as OfficialAlert[],
      c.input.wind_relation as WindRelation | null,
      c.input.user_reports_evac_order,
    );
    expect(out).toEqual(c.output);
  });

  it("AC-5: an evacuation order or Fire Warning always gives LEAVE NOW", () => {
    for (const name of ["evac_order", "fire_warning", "user_reports_order", "shelter_and_evac"]) {
      expect(g.assess.situations[name].output.level).toBe(assess.LEVEL_LEAVE_NOW);
      const c = g.assess.situations[name];
      expect(assess.assessSituation(c.input.fires, c.input.alerts, c.input.wind_relation, c.input.user_reports_evac_order).level).toBe(
        assess.LEVEL_LEAVE_NOW,
      );
    }
  });

  it("AC-5: a shelter-in-place order never says leave and quotes the order", () => {
    const c = g.assess.situations.shelter_in_place;
    const out = assess.assessSituation(c.input.fires, c.input.alerts, c.input.wind_relation, false);
    expect(out.level).toBe(assess.LEVEL_SHELTER);
    expect(out.guidance).toBe("Stay indoors. Close all windows.");
    expect(out.guidance.toLowerCase()).not.toContain("leave");
  });
});

describe("templates parity", () => {
  it("time formatting in the place's time zone", () => {
    for (const [iso, zone, want] of g.templates.format_time) expect(t.formatTime(iso, zone)).toBe(want);
  });

  it("AC-1 / AC-2 / AC-3: alert text matches Python word for word", () => {
    const f = g.templates.fires;
    const a = g.templates.alert_inputs;
    const note = t.noOtherNwsAlertsNote();
    const want = g.templates.alerts;
    expect(t.newFireAlert("Home", f.f40, note, tz)).toBe(want.new_fire);
    expect(t.newFireAlert("Home", f.f_none, note, tz)).toBe(want.new_fire_none_values);
    expect(t.growthAlert("Home", f.f150, 100, tz)).toBe(want.growth_100);
    expect(t.growthAlert("Home", f.f_frac, 1000, tz)).toBe(want.growth_1000_frac);
    expect(t.growthAlert("Parents", f.f150, 10000, tz)).toBe(want.growth_10000);
    expect(t.containmentAlert("Home", f.f_done, tz)).toBe(want.containment);
    expect(t.officialAlertText("Home", a.red, tz)).toBe(want.official_red_flag);
    expect(t.officialAlertText("Home", a.same, tz)).toBe(want.official_same_text);
    expect(t.officialAlertText("Home", a.no_body, tz)).toBe(want.official_no_body);
    expect(t.officialAlertText("Home", a.long, tz)).toBe(want.official_long);
  });

  it.each(Object.entries(g.templates.wind_lines) as [string, any][])("AC-7: wind line matches Python for %s", (_name, c) => {
    expect(t.windLine(c.wind as WindData, tz)).toBe(c.text);
  });

  it("status update matches Python", () => {
    const f = g.templates.fires;
    const a = g.templates.alert_inputs;
    expect(t.statusUpdate("Home", [], [], null, tz)).toBe(g.templates.status.calm);
    expect(t.statusUpdate("Home", [f.f150], [a.red], g.templates.status_inputs.wind, tz)).toBe(
      g.templates.status.fire_and_alert_with_wind,
    );
  });

  it("shared constants match Python", () => {
    expect(t.FEEL_UNSAFE_LINE).toBe(g.templates.constants.feel_unsafe);
    expect(t.noOtherNwsAlertsNote()).toBe(g.templates.constants.no_other_alerts);
    expect(assess.GUIDANCE_TEXT).toEqual(g.templates.constants.guidance);
  });
});
