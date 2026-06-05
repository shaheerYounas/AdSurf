import { PageHeader } from "@/components/page-header";
import { RecommendationsWorkspace } from "@/components/recommendations/recommendations-workspace";

export default function RecommendationsPage() {
  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Approval queue"
        title="AI recommendations"
        description="Review AI-assisted and rules-engine recommendations with seller-friendly evidence, export eligibility, and approval-only safety boundaries."
      />
      <RecommendationsWorkspace />
    </section>
  );
}
