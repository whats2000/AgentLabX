import { describe, it, expect } from "vitest";
import { formatRelative } from "../../src/lib/relativeTime";

describe("formatRelative", () => {
  const now = 1_700_000_000_000;

  it("returns '—' when timestamp is absent", () => {
    expect(formatRelative(undefined, now)).toBe("—");
  });

  it("returns '—' for unparseable input", () => {
    expect(formatRelative("not a date", now)).toBe("—");
  });

  it("returns 'just now' for deltas under 3 seconds", () => {
    expect(formatRelative(new Date(now - 1000).toISOString(), now)).toBe(
      "just now",
    );
  });

  it("returns seconds format for under a minute", () => {
    expect(formatRelative(new Date(now - 45_000).toISOString(), now)).toBe(
      "45s ago",
    );
  });

  it("returns minutes format for under an hour", () => {
    expect(formatRelative(new Date(now - 5 * 60_000).toISOString(), now)).toBe(
      "5m ago",
    );
  });

  it("returns hours format for under a day", () => {
    expect(
      formatRelative(new Date(now - 3 * 60 * 60_000).toISOString(), now),
    ).toBe("3h ago");
  });

  it("returns days format for under a week", () => {
    expect(
      formatRelative(new Date(now - 2 * 24 * 60 * 60_000).toISOString(), now),
    ).toBe("2d ago");
  });
});
