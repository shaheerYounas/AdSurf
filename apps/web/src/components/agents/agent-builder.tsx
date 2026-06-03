"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  Brain,
  Check,
  ClipboardList,
  Code,
  Database,
  Globe,
  Loader2,
  Mail,
  MessageSquare,
  Play,
  Plus,
  Save,
  Settings,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { humanize } from "@/lib/utils";
import {
  addAgentTool,
  cloneAgentTemplate,
  createCustomAgent,
  createSubAgent,
  deleteCustomAgent,
  deleteSubAgent,
  getAvailableTools,
  getCustomAgent,
  linkKnowledgeBase,
  listAgentMemories,
  listAgentTemplates,
  listCustomAgents,
  listKnowledgeBases,
  listSubAgents,
  removeAgentTool,
  runAgent,
  unlinkKnowledgeBase,
  updateCustomAgent,
  updateSubAgent,
  type AgentTemplate,
  type AvailableTool,
  type CustomAgent,
  type CustomAgentSummary,
  type KnowledgeBase,
  type SubAgent,
} from "@/lib/api/custom-agents";

// ── Constants ────────────────────────────────────────────────────────────────

const MODELS_BY_PROVIDER: Record<string, string[]> = {
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  anthropic: ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
  deepseek: ["deepseek-chat", "deepseek-reasoner"],
  google: ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
  local: ["llama-3.1-8b", "llama-3.1-70b", "mixtral-8x7b"],
};

const PROVIDER_OPTIONS = Object.keys(MODELS_BY_PROVIDER).map((key) => ({
  value: key,
  label: key === "deepseek" ? "DeepSeek" : key === "openai" ? "OpenAI" : key === "anthropic" ? "Anthropic" : key === "google" ? "Google" : key === "local" ? "Local" : humanize(key),
}));

const OUTPUT_FORMATS = ["text", "json", "markdown", "table", "code", "email"] as const;
const OUTPUT_FORMAT_OPTIONS = OUTPUT_FORMATS.map((f) => ({ value: f, label: humanize(f) }));
const AGENT_ROLES = ["researcher", "writer", "reviewer", "coder", "analyst", "planner", "support", "sales", "general"] as const;
const AGENT_ROLE_OPTIONS = AGENT_ROLES.map((r) => ({ value: r, label: humanize(r) }));
const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "archived", label: "Archived" },
];

const toolCategoryIcons: Record<string, React.ReactNode> = {
  web: <Globe size={14} />,
  development: <Code size={14} />,
  communication: <Mail size={14} />,
  data: <Database size={14} />,
  business: <ClipboardList size={14} />,
};

const toolCategoryColors: Record<string, string> = {
  web: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200",
  development: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-200",
  communication: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200",
  data: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200",
  business: "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-200",
};

// ── Component ────────────────────────────────────────────────────────────────

export function AgentBuilder() {
  const workspaceId = defaultWorkspaceId;
  const [agents, setAgents] = useState<CustomAgentSummary[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<CustomAgent | null>(null);
  const [availableTools, setAvailableTools] = useState<AvailableTool[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [subAgents, setSubAgents] = useState<SubAgent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"general" | "tools" | "knowledge" | "sub-agents" | "memory" | "run">("general");

  // New agent form state
  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newInstructions, setNewInstructions] = useState("");
  const [newProvider, setNewProvider] = useState("deepseek");
  const [newModel, setNewModel] = useState("deepseek-chat");
  const [newTemperature, setNewTemperature] = useState(0.7);
  const [newMemoryEnabled, setNewMemoryEnabled] = useState(false);
  const [newOutputFormat, setNewOutputFormat] = useState("text");

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editInstructions, setEditInstructions] = useState("");
  const [editProvider, setEditProvider] = useState("deepseek");
  const [editModel, setEditModel] = useState("deepseek-chat");
  const [editTemperature, setEditTemperature] = useState(0.7);
  const [editMemoryEnabled, setEditMemoryEnabled] = useState(false);
  const [editOutputFormat, setEditOutputFormat] = useState("text");
  const [editStatus, setEditStatus] = useState("draft");

  // Sub-agent form
  const [showSubForm, setShowSubForm] = useState(false);
  const [subName, setSubName] = useState("");
  const [subRole, setSubRole] = useState("researcher");
  const [subInstructions, setSubInstructions] = useState("");

  // Run state
  const [runMessage, setRunMessage] = useState("");
  const [runResult, setRunResult] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  // Template filter
  const [templateCategory, setTemplateCategory] = useState<string | null>(null);

  // Tool search
  const [toolSearch, setToolSearch] = useState("");

  useEffect(() => { void load(); }, []);

  async function load() {
    setIsLoading(true);
    try {
      setAgents(await listCustomAgents(workspaceId));
      setAvailableTools(await getAvailableTools(workspaceId));
      setKnowledgeBases(await listKnowledgeBases(workspaceId));
      setTemplates(await listAgentTemplates(workspaceId));
    } catch (err) {
      setMessage(formatApiError(err, "Could not load agent data."));
    } finally {
      setIsLoading(false);
    }
  }

  async function selectAgent(agentId: string) {
    setIsLoading(true);
    setMessage(null);
    try {
      const agent = await getCustomAgent(agentId, workspaceId);
      const subs = await listSubAgents(agentId, workspaceId);
      setSelectedAgent(agent);
      setSubAgents(subs);
      // Populate edit form
      setEditName(agent.name);
      setEditDescription(agent.description ?? "");
      setEditInstructions(agent.role_instructions ?? "");
      setEditProvider(agent.model_provider);
      setEditModel(agent.model_name);
      setEditTemperature(agent.temperature);
      setEditMemoryEnabled(agent.memory_enabled);
      setEditOutputFormat(agent.output_format);
      setEditStatus(agent.status);
    } catch (err) {
      setMessage(formatApiError(err, "Could not load agent."));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setIsSaving(true);
    setMessage(null);
    try {
      const agent = await createCustomAgent({
        name: newName,
        description: newDescription || null,
        role_instructions: newInstructions || null,
        model_provider: newProvider as CustomAgent["model_provider"],
        model_name: newModel,
        temperature: newTemperature,
        memory_enabled: newMemoryEnabled,
        output_format: newOutputFormat as CustomAgent["output_format"],
      }, workspaceId);
      setMessage(`Agent "${agent.name}" created successfully.`);
      setShowNewForm(false);
      resetNewForm();
      await load();
      await selectAgent(agent.id);
    } catch (err) {
      setMessage(formatApiError(err, "Could not create agent."));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSave() {
    if (!selectedAgent) return;
    setIsSaving(true);
    setMessage(null);
    try {
      await updateCustomAgent(selectedAgent.id, {
        name: editName,
        description: editDescription || null,
        role_instructions: editInstructions || null,
        model_provider: editProvider as CustomAgent["model_provider"],
        model_name: editModel,
        temperature: editTemperature,
        memory_enabled: editMemoryEnabled,
        output_format: editOutputFormat as CustomAgent["output_format"],
        status: editStatus as CustomAgent["status"],
      }, workspaceId);
      setMessage("Agent configuration saved.");
      await selectAgent(selectedAgent.id);
    } catch (err) {
      setMessage(formatApiError(err, "Could not save agent."));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete(agentId: string) {
    if (!confirm("Delete this agent? This action cannot be undone.")) return;
    try {
      await deleteCustomAgent(agentId, workspaceId);
      setSelectedAgent(null);
      setSubAgents([]);
      setMessage("Agent deleted.");
      await load();
    } catch (err) {
      setMessage(formatApiError(err, "Could not delete agent."));
    }
  }

  async function handleToggleTool(toolName: string) {
    if (!selectedAgent) return;
    const existing = selectedAgent.tools.find((t) => t.tool_name === toolName);
    try {
      if (existing) {
        await removeAgentTool(selectedAgent.id, existing.id, workspaceId);
        setMessage(`"${toolName}" removed.`);
      } else {
        const toolDef = availableTools.find((t) => t.tool_name === toolName);
        await addAgentTool(selectedAgent.id, {
          tool_name: toolName,
          requires_approval: toolDef?.requires_approval_by_default ?? false,
          permission_level: toolDef?.default_permission_level ?? "read",
        }, workspaceId);
        setMessage(`"${toolName}" added.`);
      }
      await selectAgent(selectedAgent.id);
    } catch (err) {
      setMessage(formatApiError(err, "Tool change failed."));
    }
  }

  async function handleToggleKb(kbId: string) {
    if (!selectedAgent) return;
    const linked = selectedAgent.knowledge_base_ids.includes(kbId);
    try {
      if (linked) {
        await unlinkKnowledgeBase(selectedAgent.id, kbId, workspaceId);
        setMessage("Knowledge base unlinked.");
      } else {
        await linkKnowledgeBase(selectedAgent.id, kbId, workspaceId);
        setMessage("Knowledge base linked.");
      }
      await selectAgent(selectedAgent.id);
    } catch (err) {
      setMessage(formatApiError(err, "Knowledge base change failed."));
    }
  }

  async function handleCreateSubAgent() {
    if (!selectedAgent || !subName.trim()) return;
    setIsSaving(true);
    try {
      await createSubAgent(selectedAgent.id, {
        name: subName,
        role: subRole,
        instructions: subInstructions,
        execution_order: subAgents.length + 1,
      }, workspaceId);
      setMessage(`Sub-agent "${subName}" created.`);
      setShowSubForm(false);
      setSubName("");
      setSubInstructions("");
      await selectAgent(selectedAgent.id);
      setSubAgents(await listSubAgents(selectedAgent.id, workspaceId));
    } catch (err) {
      setMessage(formatApiError(err, "Could not create sub-agent."));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeleteSubAgent(subAgentId: string, name: string) {
    if (!selectedAgent || !confirm(`Delete sub-agent "${name}"?`)) return;
    try {
      await deleteSubAgent(selectedAgent.id, subAgentId, workspaceId);
      setSubAgents(await listSubAgents(selectedAgent.id, workspaceId));
      setMessage(`Sub-agent "${name}" deleted.`);
    } catch (err) {
      setMessage(formatApiError(err, "Could not delete sub-agent."));
    }
  }

  async function handleRun() {
    if (!selectedAgent || !runMessage.trim()) return;
    setIsRunning(true);
    setRunResult(null);
    setMessage(null);
    try {
      const result = await runAgent(selectedAgent.id, runMessage, undefined, workspaceId);
      setRunResult(JSON.stringify(result.output_json, null, 2));
      setMessage("Agent run completed.");
    } catch (err) {
      setMessage(formatApiError(err, "Agent run failed."));
    } finally {
      setIsRunning(false);
    }
  }

  async function handleCloneTemplate(templateId: string) {
    setIsSaving(true);
    try {
      const agent = await cloneAgentTemplate(templateId, workspaceId);
      setMessage(`Template cloned as "${agent.name}".`);
      await load();
      await selectAgent(agent.id);
    } catch (err) {
      setMessage(formatApiError(err, "Could not clone template."));
    } finally {
      setIsSaving(false);
    }
  }

  function resetNewForm() {
    setNewName("");
    setNewDescription("");
    setNewInstructions("");
    setNewProvider("deepseek");
    setNewModel("deepseek-chat");
    setNewTemperature(0.7);
    setNewMemoryEnabled(false);
    setNewOutputFormat("text");
  }

  const activeToolNames = useMemo(() => new Set(selectedAgent?.tools.map((t) => t.tool_name) ?? []), [selectedAgent]);
  const activeKbIds = useMemo(() => new Set(selectedAgent?.knowledge_base_ids ?? []), [selectedAgent]);
  const filteredTools = useMemo(() => {
    if (!toolSearch.trim()) return availableTools;
    return availableTools.filter((t) =>
      t.display_name.toLowerCase().includes(toolSearch.toLowerCase()) ||
      t.description.toLowerCase().includes(toolSearch.toLowerCase()) ||
      t.category.includes(toolSearch.toLowerCase())
    );
  }, [availableTools, toolSearch]);

  const categories = useMemo(() => [...new Set(availableTools.map((t) => t.category))], [availableTools]);
  const templateCategories = useMemo(() => [...new Set(templates.map((t) => t.category))], [templates]);
  const filteredTemplates = templateCategory ? templates.filter((t) => t.category === templateCategory) : templates;

  const providerModels = useMemo(() => MODELS_BY_PROVIDER[newProvider] ?? [], [newProvider]);
  const editProviderModels = useMemo(() => MODELS_BY_PROVIDER[editProvider] ?? [], [editProvider]);

  if (isLoading && !selectedAgent && !agents.length) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="animate-spin text-indigo-500" size={32} />
      </div>
    );
  }

  return (
    <div className="min-h-screen rounded-[1.75rem] bg-slate-100 p-3 text-slate-950 dark:bg-slate-950 dark:text-white sm:p-4 lg:p-5">
      <main className="mx-auto min-w-0 max-w-[1600px] space-y-6">
        {message ? (
          <div className="rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm font-semibold text-indigo-900 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
            {message}
          </div>
        ) : null}

        {/* Agent List + Templates */}
        <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
          {/* Sidebar: Agent List */}
          <aside className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">My Agents</h2>
              <Button onClick={() => { setShowNewForm(true); setSelectedAgent(null); }} type="button" variant="primary" className="h-8 px-3 text-xs"><Plus size={14} /> New</Button>
            </div>
            <div className="mt-3 space-y-1">
              {agents.map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => selectAgent(agent.id)}
                  className={`w-full rounded-2xl px-3 py-2.5 text-left text-sm transition ${selectedAgent?.id === agent.id ? "border border-indigo-200 bg-indigo-50 dark:border-indigo-300/25 dark:bg-indigo-300/10" : "hover:bg-slate-100 dark:hover:bg-white/5"}`}
                >
                  <div className="flex items-center gap-2">
                    <Bot size={16} className="shrink-0 text-slate-400" />
                    <span className="truncate font-semibold">{agent.name}</span>
                    <span className={`ml-auto shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${agent.status === "active" ? "bg-emerald-100 text-emerald-800" : agent.status === "draft" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600"}`}>{agent.status}</span>
                  </div>
                  <div className="mt-1 flex gap-3 text-[11px] text-slate-500">
                    <span>{agent.model_provider}/{agent.model_name}</span>
                    <span>{agent.tool_count} tools</span>
                    <span>{agent.sub_agent_count} sub-agents</span>
                  </div>
                </button>
              ))}
              {!agents.length && <p className="py-6 text-center text-sm text-slate-400">No agents created yet. Click "New" to get started.</p>}
            </div>

            {/* Templates section */}
            <div className="mt-6 border-t border-slate-200 pt-4 dark:border-white/10">
              <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Templates</h3>
              <div className="mt-2 flex flex-wrap gap-1">
                {templateCategories.map((cat) => (
                  <button key={cat} onClick={() => setTemplateCategory(templateCategory === cat ? null : cat)} className={`rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize ${templateCategory === cat ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300"}`}>{cat}</button>
                ))}
              </div>
              <div className="mt-2 space-y-1 max-h-60 overflow-y-auto">
                {filteredTemplates.map((t) => (
                  <button key={t.id} onClick={() => handleCloneTemplate(t.id)} className="w-full rounded-2xl px-3 py-2 text-left text-xs transition hover:bg-slate-100 dark:hover:bg-white/5">
                    <p className="font-semibold">{t.name}</p>
                    <p className="mt-0.5 line-clamp-2 text-slate-500">{t.description}</p>
                  </button>
                ))}
              </div>
            </div>
          </aside>

          {/* Main Content */}
          <div className="min-w-0 space-y-6">
            {/* New Agent Form */}
            {showNewForm && !selectedAgent && (
              <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
                <h2 className="heading-fluid mb-4 font-semibold tracking-tight text-slate-950 dark:text-white">Create New Agent</h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-semibold">Agent Name *</label>
                    <input className="mt-1 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm dark:border-white/10 dark:bg-white/5" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g., Sales Research Agent" />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold">Description</label>
                    <input className="mt-1 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm dark:border-white/10 dark:bg-white/5" value={newDescription} onChange={(e) => setNewDescription(e.target.value)} placeholder="What this agent does" />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-sm font-semibold">Role / Instructions</label>
                    <textarea className="mt-1 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm dark:border-white/10 dark:bg-white/5" rows={3} value={newInstructions} onChange={(e) => setNewInstructions(e.target.value)} placeholder="You are an expert..." />
                  </div>
                  <Select
                    label="Model Provider"
                    value={newProvider}
                    options={PROVIDER_OPTIONS}
                    onChange={(v) => { setNewProvider(v); setNewModel(MODELS_BY_PROVIDER[v]?.[0] ?? ""); }}
                  />
                  <Select
                    label="Model"
                    value={newModel}
                    options={providerModels.map((m) => ({ value: m, label: m }))}
                    onChange={(v) => setNewModel(v)}
                  />
                  <div>
                    <label className="block text-sm font-semibold">Temperature: {newTemperature}</label>
                    <input className="mt-1 w-full" type="range" min="0" max="2" step="0.1" value={newTemperature} onChange={(e) => setNewTemperature(parseFloat(e.target.value))} />
                  </div>
                  <Select
                    label="Output Format"
                    value={newOutputFormat}
                    options={OUTPUT_FORMAT_OPTIONS}
                    onChange={(v) => setNewOutputFormat(v)}
                  />
                  <div className="sm:col-span-2">
                    <Switch
                      label="Enable Memory"
                      checked={newMemoryEnabled}
                      onChange={setNewMemoryEnabled}
                      helperText="Persist context across conversations"
                    />
                  </div>
                </div>
                <div className="mt-4 flex gap-3">
                  <Button onClick={handleCreate} disabled={isSaving || !newName.trim()} type="button" variant="primary">
                    {isSaving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                    Create Agent
                  </Button>
                  <Button onClick={() => { setShowNewForm(false); resetNewForm(); }} type="button" variant="secondary">Cancel</Button>
                </div>
              </section>
            )}

            {/* Selected Agent Editor */}
            {selectedAgent && (
              <>
                {/* Tab Navigation */}
                <div className="-mx-1 overflow-x-auto px-1 pb-1 scrollbar-none">
                  <div className="flex min-w-max gap-2">
                    {(["general", "tools", "knowledge", "sub-agents", "memory", "run"] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold capitalize transition ${
                          activeTab === tab
                            ? "bg-indigo-600 text-white shadow-sm"
                            : "bg-white text-slate-600 hover:bg-slate-100 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
                        }`}
                      >
                        {tab === "general" && <Settings size={14} />}
                        {tab === "tools" && <Globe size={14} />}
                        {tab === "knowledge" && <Database size={14} />}
                        {tab === "sub-agents" && <Users size={14} />}
                        {tab === "memory" && <Brain size={14} />}
                        {tab === "run" && <Play size={14} />}
                        {tab}
                      </button>
                    ))}
                  </div>
                </div>

                {/* General Settings Tab */}
                {activeTab === "general" && (
                  <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
                    <h2 className="heading-fluid mb-4 font-semibold tracking-tight text-slate-950 dark:text-white">General Configuration</h2>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label className="block text-sm font-semibold">Agent Name</label>
                        <input className="mt-1 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm dark:border-white/10 dark:bg-white/5" value={editName} onChange={(e) => setEditName(e.target.value)} />
                      </div>
                      <Select
                        label="Status"
                        value={editStatus}
                        options={STATUS_OPTIONS}
                        onChange={(v) => setEditStatus(v)}
                      />
                      <div className="sm:col-span-2">
                        <label className="block text-sm font-semibold">Description</label>
                        <input className="mt-1 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm dark:border-white/10 dark:bg-white/5" value={editDescription} onChange={(e) => setEditDescription(e.target.value)} />
                      </div>
                      <div className="sm:col-span-2">
                        <label className="block text-sm font-semibold">Role / Instructions (System Prompt)</label>
                        <textarea className="mt-1 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm dark:border-white/10 dark:bg-white/5" rows={5} value={editInstructions} onChange={(e) => setEditInstructions(e.target.value)} placeholder="You are an expert..." />
                      </div>
                      <Select
                        label="Model Provider"
                        value={editProvider}
                        options={PROVIDER_OPTIONS}
                        onChange={(v) => { setEditProvider(v); setEditModel(MODELS_BY_PROVIDER[v]?.[0] ?? ""); }}
                      />
                      <Select
                        label="Model"
                        value={editModel}
                        options={editProviderModels.map((m) => ({ value: m, label: m }))}
                        onChange={(v) => setEditModel(v)}
                      />
                      <div>
                        <label className="block text-sm font-semibold">Temperature: {editTemperature}</label>
                        <input className="mt-1 w-full" type="range" min="0" max="2" step="0.1" value={editTemperature} onChange={(e) => setEditTemperature(parseFloat(e.target.value))} />
                      </div>
                      <Select
                        label="Output Format"
                        value={editOutputFormat}
                        options={OUTPUT_FORMAT_OPTIONS}
                        onChange={(v) => setEditOutputFormat(v)}
                      />
                      <div className="sm:col-span-2">
                        <Switch
                          label="Enable Memory"
                          checked={editMemoryEnabled}
                          onChange={setEditMemoryEnabled}
                          helperText="Persist context across conversations"
                        />
                      </div>
                    </div>
                    <div className="mt-4 flex gap-3">
                      <Button onClick={handleSave} disabled={isSaving} type="button" variant="primary">
                        {isSaving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                        Save Configuration
                      </Button>
                      <Button onClick={() => handleDelete(selectedAgent.id)} type="button" variant="danger">
                        <Trash2 size={16} /> Delete
                      </Button>
                    </div>
                  </section>
                )}

                {/* Tools Tab */}
                {activeTab === "tools" && (
                  <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <h2 className="heading-fluid font-semibold tracking-tight text-slate-950 dark:text-white">Tools & Actions</h2>
                        <p className="mt-1 text-sm text-slate-500">{activeToolNames.size} tools enabled. Dangerous tools require human approval.</p>
                      </div>
                      <input className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm dark:border-white/10 dark:bg-white/5" placeholder="Search tools..." value={toolSearch} onChange={(e) => setToolSearch(e.target.value)} />
                    </div>
                    {categories.map((category) => {
                      const catTools = filteredTools.filter((t) => t.category === category);
                      if (!catTools.length) return null;
                      return (
                        <div key={category} className="mt-4">
                          <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">{category}</h3>
                          <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                            {catTools.map((tool) => {
                              const isActive = activeToolNames.has(tool.tool_name);
                              return (
                                <button
                                  key={tool.tool_name}
                                  onClick={() => handleToggleTool(tool.tool_name)}
                                  className={`flex items-start gap-3 rounded-2xl border p-3 text-left transition ${isActive ? "border-indigo-300 bg-indigo-50 dark:border-indigo-300/30 dark:bg-indigo-300/10" : "border-slate-200 bg-slate-50 hover:border-indigo-200 dark:border-white/10 dark:bg-white/5"}`}
                                >
                                  <span className={`mt-0.5 rounded-full p-1.5 ${toolCategoryColors[category] ?? "bg-slate-100"}`}>{toolCategoryIcons[category]}</span>
                                  <div className="min-w-0 flex-1">
                                    <p className="text-sm font-semibold">{tool.display_name}</p>
                                    <p className="mt-0.5 text-xs text-slate-500 line-clamp-2">{tool.description}</p>
                                    <div className="mt-1.5 flex flex-wrap gap-1">
                                      {tool.is_dangerous && <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-700 dark:bg-rose-900/30 dark:text-rose-300">⚠ Dangerous</span>}
                                      {tool.requires_approval_by_default && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">Needs approval</span>}
                                    </div>
                                  </div>
                                  {isActive && <Check size={16} className="shrink-0 text-indigo-600" />}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </section>
                )}

                {/* Knowledge Base Tab */}
                {activeTab === "knowledge" && (
                  <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
                    <h2 className="heading-fluid mb-4 font-semibold tracking-tight text-slate-950 dark:text-white">Knowledge Bases</h2>
                    <p className="text-sm text-slate-500">Connect documents, PDFs, and data to give your agent context during conversations.</p>
                    {!knowledgeBases.length ? (
                      <div className="mt-4 rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-white/15">
                        <Database size={24} className="mx-auto mb-2 text-slate-400" />
                        <p>No knowledge bases yet. Create one by uploading documents.</p>
                        <Button className="mt-3" onClick={async () => {
                          const name = prompt("Knowledge base name:");
                          if (name) {
                            const { createKnowledgeBase } = await import("@/lib/api/custom-agents");
                            try { await createKnowledgeBase({ name }, workspaceId); await load(); setMessage(`Knowledge base "${name}" created.`); } catch (err) { setMessage(formatApiError(err, "Failed.")); }
                          }
                        }} type="button" variant="primary"><Plus size={14} /> Create Knowledge Base</Button>
                      </div>
                    ) : (
                      <>
                        <Button className="mt-3 mb-4" onClick={async () => {
                          const name = prompt("Knowledge base name:");
                          if (name) {
                            const { createKnowledgeBase } = await import("@/lib/api/custom-agents");
                            try { await createKnowledgeBase({ name }, workspaceId); await load(); setMessage(`Knowledge base "${name}" created.`); } catch (err) { setMessage(formatApiError(err, "Failed.")); }
                          }
                        }} type="button" variant="secondary"><Plus size={14} /> New Knowledge Base</Button>
                        <div className="grid gap-3 sm:grid-cols-2">
                          {knowledgeBases.map((kb) => {
                            const isLinked = activeKbIds.has(kb.id);
                            return (
                              <button
                                key={kb.id}
                                onClick={() => handleToggleKb(kb.id)}
                                className={`flex items-start gap-3 rounded-2xl border p-3 text-left transition ${isLinked ? "border-indigo-300 bg-indigo-50 dark:border-indigo-300/30 dark:bg-indigo-300/10" : "border-slate-200 bg-slate-50 hover:border-indigo-200 dark:border-white/10 dark:bg-white/5"}`}
                              >
                                <Database size={18} className="shrink-0 text-slate-400" />
                                <div className="min-w-0 flex-1">
                                  <p className="text-sm font-semibold">{kb.name}</p>
                                  <p className="mt-0.5 text-xs text-slate-500">{kb.file_count} files · {kb.chunk_count} chunks · {kb.status}</p>
                                </div>
                                {isLinked && <Check size={16} className="shrink-0 text-indigo-600" />}
                              </button>
                            );
                          })}
                        </div>
                      </>
                    )}
                  </section>
                )}

                {/* Sub-Agents Tab */}
                {activeTab === "sub-agents" && (
                  <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
                    <div className="flex items-center justify-between">
                      <div>
                        <h2 className="heading-fluid font-semibold tracking-tight text-slate-950 dark:text-white">Sub-Agents Team</h2>
                        <p className="mt-1 text-sm text-slate-500">{subAgents.length} specialist agents. Sub-agents execute in order.</p>
                      </div>
                      <Button onClick={() => setShowSubForm(true)} type="button" variant="primary"><Plus size={14} /> Add Sub-Agent</Button>
                    </div>
                    {showSubForm && (
                      <div className="mt-4 rounded-2xl border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-300/25 dark:bg-indigo-300/10">
                        <div className="grid gap-3 sm:grid-cols-3">
                          <div>
                            <label className="block text-sm font-semibold">Name</label>
                            <input className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-950/70" value={subName} onChange={(e) => setSubName(e.target.value)} placeholder="e.g., Research Agent" />
                          </div>
                          <Select
                            label="Role"
                            value={subRole}
                            options={AGENT_ROLE_OPTIONS}
                            onChange={(v) => setSubRole(v)}
                          />
                          <div className="flex items-end gap-2">
                            <Button onClick={handleCreateSubAgent} disabled={isSaving || !subName.trim()} type="button" variant="primary" className="flex-1">{isSaving ? <Loader2 className="animate-spin" size={14} /> : <Plus size={14} />} Add</Button>
                            <Button onClick={() => setShowSubForm(false)} type="button" variant="secondary"><X size={14} /></Button>
                          </div>
                        </div>
                        <div className="mt-3">
                          <label className="block text-sm font-semibold">Instructions</label>
                          <textarea className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-950/70" rows={2} value={subInstructions} onChange={(e) => setSubInstructions(e.target.value)} placeholder="Instructions for this sub-agent..." />
                        </div>
                      </div>
                    )}
                    <div className="mt-4 space-y-2">
                      {subAgents.map((sub, idx) => (
                        <div key={sub.id} className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5">
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700 dark:bg-indigo-800/50 dark:text-indigo-200">{idx + 1}</span>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold">{sub.name}</p>
                            <p className="text-xs text-slate-500">{sub.role} · {sub.enabled ? "Enabled" : "Disabled"}</p>
                            <p className="mt-0.5 text-xs text-slate-400 line-clamp-1">{sub.instructions || "No instructions set"}</p>
                          </div>
                          <div className="flex gap-1">
                            <Button onClick={async () => {
                              const newState = !sub.enabled;
                              try {
                                await updateSubAgent(selectedAgent!.id, sub.id, { enabled: newState }, workspaceId);
                                setSubAgents(await listSubAgents(selectedAgent!.id, workspaceId));
                              } catch (err) { setMessage(formatApiError(err, "Update failed.")); }
                            }} type="button" variant="secondary" className="h-8 w-8 p-0" title={sub.enabled ? "Disable" : "Enable"}>{sub.enabled ? <Check size={14} className="text-emerald-600" /> : <X size={14} className="text-slate-400" />}</Button>
                            <Button onClick={() => handleDeleteSubAgent(sub.id, sub.name)} type="button" variant="secondary" className="h-8 w-8 p-0 text-rose-500" title="Delete"><Trash2 size={14} /></Button>
                          </div>
                        </div>
                      ))}
                      {!subAgents.length && !showSubForm && (
                        <p className="py-6 text-center text-sm text-slate-400">No sub-agents. Add specialist agents to create a multi-agent team.</p>
                      )}
                    </div>
                    {/* Workflow Visualization */}
                    {subAgents.length > 0 && (
                      <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Execution Flow</p>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white">Supervisor</span>
                          {subAgents.sort((a, b) => a.execution_order - b.execution_order).map((sub) => (
                            <span key={sub.id} className="flex items-center gap-2">
                              <span className="text-slate-400">→</span>
                              <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-white">{sub.name}</span>
                            </span>
                          ))}
                          <span className="text-slate-400">→</span>
                          <span className="rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white">Output</span>
                        </div>
                      </div>
                    )}
                  </section>
                )}

                {/* Memory Tab */}
                {activeTab === "memory" && (
                  <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
                    <div className="flex items-start gap-3">
                      <Brain size={20} className="shrink-0 text-indigo-600" />
                      <div>
                        <h2 className="heading-fluid font-semibold tracking-tight text-slate-950 dark:text-white">Memory Settings</h2>
                        <p className="mt-1 text-sm text-slate-500">When enabled, the agent remembers user preferences, project context, and past decisions across conversations. Memories are stored with vector embeddings for semantic recall.</p>
                      </div>
                    </div>
                    <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
                      <Switch
                        label="Enable Long-Term Memory"
                        checked={editMemoryEnabled}
                        onChange={(checked) => { setEditMemoryEnabled(checked); }}
                      />
                      {editMemoryEnabled && (
                        <Select
                          label="Memory TTL"
                          value={String(selectedAgent?.memory_ttl_days ?? 30)}
                          options={[
                            { value: "7", label: "7 days" },
                            { value: "30", label: "30 days" },
                            { value: "90", label: "90 days" },
                            { value: "365", label: "1 year" },
                          ]}
                          onChange={(v) => {
                            if (selectedAgent) updateCustomAgent(selectedAgent.id, { memory_ttl_days: parseInt(v) }, workspaceId).then(() => selectAgent(selectedAgent!.id));
                          }}
                          className="w-40"
                        />
                      )}
                    </div>
                    <div className="mt-4 rounded-2xl border border-dashed border-slate-300 p-6 text-center dark:border-white/15">
                      <Brain size={24} className="mx-auto mb-2 text-slate-400" />
                      <p className="text-sm text-slate-500">Memory entries are automatically created from conversations when memory is enabled. You can view and manage memories for each agent.</p>
                    </div>
                    <Button className="mt-4" onClick={() => { if (selectedAgent) { listAgentMemories(selectedAgent.id, workspaceId).then((memories) => { setMessage(`${memories.length} memories found for this agent.`); }).catch(() => setMessage("Could not load memories.")); } }} type="button" variant="secondary"><MessageSquare size={14} /> View Memories</Button>
                  </section>
                )}

                {/* Run Tab */}
                {activeTab === "run" && (
                  <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
                    <h2 className="heading-fluid mb-4 font-semibold tracking-tight text-slate-950 dark:text-white">Test Your Agent</h2>
                    <p className="mb-4 text-sm text-slate-500">Send a message to test how your agent responds. The runtime follows: Supervisor → Sub-agents → Tools → Reviewer → Output Format → Approval Check.</p>
                    <textarea className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm dark:border-white/10 dark:bg-white/5" rows={3} value={runMessage} onChange={(e) => setRunMessage(e.target.value)} placeholder="e.g., Research competitor websites and write a summary" />
                    <div className="mt-3 flex gap-3">
                      <Button onClick={handleRun} disabled={isRunning || !runMessage.trim()} type="button" variant="primary">
                        {isRunning ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
                        Run Agent
                      </Button>
                    </div>
                    {runResult && (
                      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-slate-950/70">
                        <p className="mb-2 text-xs font-semibold uppercase text-slate-500">Agent Response</p>
                        <pre className="whitespace-pre-wrap break-words text-sm text-slate-800 dark:text-slate-200 font-mono">{runResult}</pre>
                      </div>
                    )}
                  </section>
                )}
              </>
            )}

            {/* Empty State */}
            {!selectedAgent && !showNewForm && (
              <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white p-8 dark:border-white/15 dark:bg-slate-950/70">
                <div className="text-center">
                  <Bot size={48} className="mx-auto text-slate-300 dark:text-slate-600" />
                  <h2 className="mt-4 text-xl font-semibold text-slate-700 dark:text-slate-300">Build Your AI Agent</h2>
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Select an agent from the sidebar or create a new one. You can also clone a template to get started quickly.</p>
                  <Button className="mt-4" onClick={() => setShowNewForm(true)} type="button" variant="primary"><Plus size={16} /> Create New Agent</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
