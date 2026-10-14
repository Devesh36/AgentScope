import { describe, expect, it } from "vitest";
import { readExplorerFilters, viewLink } from "../lib/explorer-filters";

describe("external explorer links", () => {
  it("rejects malformed pages and invalid dropdown values before querying", () => {
    for (const page of ["-1", "0", "1.5", "NaN", "Infinity", "1000001", "99999999999999999999"]) {
      const params = new URLSearchParams({ page, status: "unknown", severity: "unknown", sort: "unknown", q: "a".repeat(250) });
      expect(readExplorerFilters(params, "incidents")).toEqual({ search: "a".repeat(200), status: "active", severity: "all", sort: "newest", offset: 0 });
    }
  });

  it("shares only supported filters and the chosen workspace, excluding arbitrary secrets", () => {
    const shared = new URL(viewLink("https://admin:secret@workspace.example/runs?project=old&token=secret&password=private&q=A%26B&status=failed&page=2#private", "selected", 168, "live", "runs"));
    expect(shared.origin + shared.pathname).toBe("https://workspace.example/runs");
    expect(Object.fromEntries(shared.searchParams)).toEqual({ project: "selected", q: "A&B", status: "failed", page: "2", hours: "168", source: "live" });
    expect(shared.hash).toBe("");
    expect(shared.username).toBe("");
    expect(shared.password).toBe("");
  });
});
