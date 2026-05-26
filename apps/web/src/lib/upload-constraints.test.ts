import { describe, expect, it } from "vitest";
import { MAX_UPLOAD_FILE_SIZE_BYTES, hasAcceptedUploadExtension } from "./upload-constraints";

describe("upload constraints", () => {
  it("accepts only Batch 3 upload extensions", () => {
    expect(hasAcceptedUploadExtension("keywords.csv")).toBe(true);
    expect(hasAcceptedUploadExtension("keywords.xlsx")).toBe(true);
    expect(hasAcceptedUploadExtension("keywords.pdf")).toBe(false);
  });

  it("uses the 25 MB MVP limit", () => {
    expect(MAX_UPLOAD_FILE_SIZE_BYTES).toBe(25 * 1024 * 1024);
  });
});
