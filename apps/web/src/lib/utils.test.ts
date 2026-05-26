import { describe, expect, it } from "vitest";

import { cn } from "./utils";

describe("cn", () => {
  it("joins truthy class names and omits empty values", () => {
    expect(cn("base", false, null, undefined, "active")).toBe("base active");
  });
});
