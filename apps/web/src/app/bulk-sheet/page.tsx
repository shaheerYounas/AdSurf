import { BulkSheetWorkspace } from "@/components/products/bulk-sheet-workspace";

export const metadata = {
  title: "Bulk Sheet Viewer | AdSurf",
  description: "Inspect your Amazon account structure — campaigns, ad groups, keywords, and current bids.",
};

export default function BulkSheetPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <BulkSheetWorkspace />
    </div>
  );
}
