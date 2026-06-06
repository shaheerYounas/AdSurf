import { BulkImportWorkspace } from "@/components/products/bulk-import-workspace";

export const metadata = {
  title: "Bulk import products | AdSurf",
  description: "Upload a CSV or XLSX file to create product profiles after review and confirmation.",
};

export default async function BulkImportPage({
  searchParams,
}: {
  searchParams: Promise<{ import_id?: string }>;
}) {
  const { import_id } = await searchParams;
  return <BulkImportWorkspace initialImportId={import_id} />;
}
