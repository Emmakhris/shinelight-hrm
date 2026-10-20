import { describe, expect, it } from "vitest";
import { errorMessage } from "./api/client";
import { fmtDate, fmtMoney, titleCase } from "./utils";

describe("formatting (Ghana locale)", () => {
  it("formats dates as DD/MM/YYYY", () => {
    expect(fmtDate("2026-03-06")).toBe("06/03/2026");
    expect(fmtDate(null)).toBe("—");
  });
  it("formats cedi amounts with two decimals", () => {
    expect(fmtMoney("3945.25")).toBe("GHS 3,945.25");
    expect(fmtMoney(0)).toBe("GHS 0.00");
    expect(fmtMoney(undefined)).toBe("—");
  });
  it("title-cases codes", () => {
    expect(titleCase("national_service")).toBe("National Service");
  });
});

describe("errorMessage", () => {
  it("reads DRF detail and field errors", () => {
    expect(errorMessage({ response: { data: { detail: "Insufficient balance" } } })).toBe("Insufficient balance");
    expect(errorMessage({ response: { data: { end_date: ["Required."] } } })).toBe("end date: Required.");
  });
});
