import { exports } from "cloudflare:workers";
import { describe, expect, it } from "vitest";

describe("setup", () => {
  it("health endpoint responds", async () => {
    const res = await exports.default.fetch("https://example.com/api/health");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
  });
});
