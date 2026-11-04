import { describe, expect, it } from "vitest";
import { formatDate, formatDistance, formatPercent } from "./format";

describe("formatPercent", () => {
  it.each([
    [0.25, "25%"],
    [0.1292, "13%"],
    [0, "0%"],
    [1, "100%"],
  ])("%d → %s", (fraction, expected) => {
    expect(formatPercent(fraction)).toBe(expected);
  });
});

describe("formatDistance", () => {
  it.each([
    [1.234, "1.2 km"],
    [10, "10 km"],
    [0.432, "430 m"],
    [0.004, "0 m"],
  ])("%d km → %s", (km, expected) => {
    expect(formatDistance(km)).toBe(expected);
  });
});

describe("formatDate", () => {
  it("reads an ISO date as that day wherever the browser is", () => {
    expect(formatDate("2026-11-08")).toBe("Sun 8 Nov");
  });
});
