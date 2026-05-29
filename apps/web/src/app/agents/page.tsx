import { AgentControlCenter } from "@/components/agents/agent-control-center";

export default function AgentsPage() {
  return (
    <section className="rounded-[1.75rem] bg-slate-100 p-3 text-slate-950 dark:bg-slate-950 dark:text-white sm:p-4 lg:p-5">
      <AgentControlCenter />
    </section>
  );
}
