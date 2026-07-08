import { describe, expect, it } from "vitest";
import { clampPage, paginate } from "./pagination";

describe("paginate", () => {
  it("slices the requested page", () => {
    const result = paginate([...Array(120).keys()], 2, 50);
    expect(result.pageItems[0]).toBe(50);
    expect(result.pageItems).toHaveLength(50);
    expect(result.pageCount).toBe(3);
    expect(result.totalItems).toBe(120);
    expect(result.page).toBe(2);
  });

  it("clamps overflowing pages when results shrink", () => {
    expect(clampPage(9, 120, 50)).toBe(3);
    expect(paginate([...Array(10).keys()], 9, 50).page).toBe(1);
  });

  it("handles empty lists as a single empty page", () => {
    expect(paginate([], 1, 50)).toEqual({ pageItems: [], page: 1, pageCount: 1, totalItems: 0 });
  });

  it("normalizes nonsense input", () => {
    expect(clampPage(0, 100, 50)).toBe(1);
    expect(clampPage(Number.NaN, 100, 50)).toBe(1);
    expect(paginate([1, 2, 3], 1, 0).pageItems).toEqual([1]);
  });
});
