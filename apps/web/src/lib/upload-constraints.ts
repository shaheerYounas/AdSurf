export const MAX_UPLOAD_FILE_SIZE_BYTES = 25 * 1024 * 1024;
export const ACCEPTED_UPLOAD_EXTENSIONS = [".csv", ".xls", ".xlsx"] as const;
export const ACCEPTED_UPLOAD_MIME_TYPES = [
  "text/csv",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
] as const;

export function hasAcceptedUploadExtension(filename: string) {
  const lower = filename.toLowerCase();
  return ACCEPTED_UPLOAD_EXTENSIONS.some((extension) => lower.endsWith(extension));
}
