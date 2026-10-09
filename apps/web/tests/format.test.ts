import { describe, expect, it } from "vitest";
import { duration, money, spanDepth } from "../lib/format";
describe("trace presentation", () => {
  it("keeps unknown costs distinct from zero", () => {
    expect(money(null)).toBe("Unavailable");
    expect(money(0)).toBe("$0.00");
    expect(money(0.0012)).toBe("$0.0012");
  });
  it("formats actual execution durations", () => {
    expect(duration(50)).toBe("50ms");
    expect(duration(1500)).toBe("1.50s");
    expect(duration(120000)).toBe("2.0m");
    expect(duration(null)).toBe("—");
  });
  it("supports out-of-order nesting, orphan spans, and malformed cycles", () => {
    const spans = [
      { span_id: "child", parent_span_id: "root" },
      { span_id: "root" },
    ];
    expect(spanDepth(spans[0], spans)).toBe(1);
    expect(
      spanDepth({ span_id: "orphan", parent_span_id: "missing" }, spans),
    ).toBe(0);
    expect(
      spanDepth({ span_id: "a", parent_span_id: "b" }, [
        { span_id: "a", parent_span_id: "b" },
        { span_id: "b", parent_span_id: "a" },
      ]),
    ).toBe(1);
  });
});
