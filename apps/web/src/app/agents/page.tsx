import { PageHeader } from "@/components/page-header";
import { AgentControlCenter } from "@/components/agents/agent-control-center";

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Agent operations"
        title="Agent Control Center"
        description="Inspect, configure, pause, stop, rerun, and audit monitoring agents without allowing live Amazon Ads execution."
      />
      <AgentControlCenter />
    </div>
  );
}
