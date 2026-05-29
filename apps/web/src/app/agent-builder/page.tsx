import { PageHeader } from "@/components/page-header";
import { AgentBuilder } from "@/components/agents/agent-builder";

export default function AgentBuilderPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Agent builder"
        title="AI Agent Builder"
        description="Create and configure custom AI agents with tools, knowledge bases, sub-agents, memory, and human approval controls."
      />
      <AgentBuilder />
    </div>
  );
}