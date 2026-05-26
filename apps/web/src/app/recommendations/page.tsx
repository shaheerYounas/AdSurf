import { PageHeader } from "@/components/page-header";
import { RecommendationsWorkspace } from "@/components/recommendations/recommendations-workspace";

export default function RecommendationsPage() {
  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Approval queue"
        title="Agent recommendations"
        description="Review rule-backed bid, pause, watch, and negative keyword recommendations with agent explanations. Human decisions are required before any manual action."
      />
      <RecommendationsWorkspace />
    </section>
  );
}
