import { BulkImportWorkspace } from "@/components/products/bulk-import-workspace";

export const metadata = {
  title: "Bulk import products | AdSurf",
  description: "Upload a CSV or XLSX file to create product profiles after review and confirmation.",
};

export default function BulkImportPage() {
  return <BulkImportWorkspace />;
}
