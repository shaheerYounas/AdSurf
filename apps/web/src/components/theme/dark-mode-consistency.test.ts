import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const files = [
  "src/components/page-header.tsx",
  "src/components/products/product-setup-form.tsx",
  "src/components/products/product-detail-panel.tsx",
  "src/components/uploads/upload-list.tsx",
  "src/components/uploads/upload-initialization-form.tsx",
  "src/components/uploads/column-mapping-workspace.tsx",
  "src/components/monitoring/monitoring-workspace.tsx",
];

describe("dark mode consistency", () => {
  it.each(files)("%s includes dark-mode surface classes", (file) => {
    const source = readFileSync(file, "utf-8");

    expect(source).toContain("dark:border-white/10");
    expect(source).toMatch(/dark:bg-(slate-950\/70|white\/5|\[linear-gradient)/);
    expect(source).toMatch(/dark:text-(white|slate-300|slate-200)/);
  });
});
