"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, ClipboardCheck, GitBranch, ShieldCheck, Sparkles, UploadCloud, Users, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const STORAGE_KEY = "adsurf-onboarding-completed";
const RESTART_EVENT = "adsurf:restart-tour";

type Step = {
  title: string;
  body: string;
  highlights: string[];
  icon: typeof Sparkles;
};

const STEPS: Step[] = [
  {
    title: "Welcome to AdSurf",
    icon: Sparkles,
    body: "AdSurf is your AI-native Amazon Ads recommendation control center. AI suggests; humans approve. No live Amazon Ads changes ever execute from this app — every decision is human-signed and audit-logged.",
    highlights: [
      "Multi-agent workflow across ingest → analysis → recommendation",
      "Safe mode by default — recommendations only",
      "Light, dark, and system theme switcher in the top bar",
    ],
  },
  {
    title: "Upload an Amazon Ads report",
    icon: UploadCloud,
    body: "Start by uploading an account-level report or bulk sheet (CSV / XLSX). AdSurf auto-detects the report type, groups entities, and prepares inputs for the agent team.",
    highlights: [
      "Drop your file into the Upload panel",
      "Watch the Completed / Running / Failed / Needs approval counters",
      "Each upload becomes an audit-anchored import record",
    ],
  },
  {
    title: "Visualize the workflow",
    icon: GitBranch,
    body: "The Workflow Canvas shows how agents pass data from raw report → cleaned entities → recommendations → approval queue. Each node is an agent; each edge is a data handoff.",
    highlights: [
      "Click a node to focus that agent in the Inspector",
      "Edges show real-time data flow direction",
      "Use Simple vs Advanced mode for the level of detail you want",
    ],
  },
  {
    title: "Operate the agent team",
    icon: Users,
    body: "Each agent card exposes Configure (tune mode/provider/strictness) and View trace (see the latest run). Use bulk controls — Pause, Resume, Stop, Rerun — to manage the whole team at once.",
    highlights: [
      "Configure switches deterministic / AI / hybrid behavior per agent",
      "View trace opens the inspector with run details and events",
      "Pause / Resume / Stop affect every agent in the workspace",
    ],
  },
  {
    title: "Approve recommendations",
    icon: ClipboardCheck,
    body: "Recommendations land in the Approval queue with full reasoning, evidence, and impact. Approve to record a human decision; reject to file an audit-logged rejection. No Amazon Ads change is ever executed by AdSurf.",
    highlights: [
      "Each approval is permanently audit-logged",
      "Rejections capture the human reasoning",
      "Filter by source, priority, or recommendation type",
    ],
  },
  {
    title: "You're ready",
    icon: CheckCircle2,
    body: "Use the theme toggle to switch between light, dark, or system mode at any time. Re-open this guide whenever you need it — there's a 'Replay tour' button at the bottom of every page footer.",
    highlights: [
      "Safe mode is on — recommendation only",
      "All actions require human approval",
      "Press Esc to close this tour at any time",
    ],
  },
];

/**
 * First-run onboarding overlay. Shows once per browser (tracked in localStorage),
 * and can be re-opened via a window event `adsurf:restart-tour`.
 */
export function OnboardingTour() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  // On mount, decide whether to auto-show the tour.
  useEffect(() => {
    try {
      const done = window.localStorage.getItem(STORAGE_KEY);
      if (!done) setOpen(true);
    } catch {
      // localStorage unavailable — skip auto-open rather than throw.
    }
    const restart = () => {
      setStep(0);
      setOpen(true);
    };
    window.addEventListener(RESTART_EVENT, restart);
    return () => window.removeEventListener(RESTART_EVENT, restart);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // ignore
    }
  }, []);

  // Esc closes; arrow keys navigate.
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "ArrowRight") setStep((s) => Math.min(s + 1, STEPS.length - 1));
      if (event.key === "ArrowLeft") setStep((s) => Math.max(s - 1, 0));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, close]);

  if (!open) return <ReplayTourButton />;

  const current = STEPS[step];
  const Icon = current.icon;
  const isLast = step === STEPS.length - 1;

  return (
    <>
      <div
        aria-hidden="true"
        className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-sm dark:bg-slate-950/70"
        onClick={close}
      />
      <div
        aria-labelledby="onboarding-title"
        aria-modal="true"
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
      >
        <div className="relative w-full max-w-2xl overflow-hidden rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-950/20 dark:border-white/10 dark:bg-slate-950 sm:p-8">
          <button
            aria-label="Close tour"
            className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition hover:border-slate-300 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:text-white"
            onClick={close}
            type="button"
          >
            <X size={16} />
          </button>

          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 dark:bg-indigo-500">
              <Icon aria-hidden="true" size={22} />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-indigo-600 dark:text-indigo-300">
                Step {step + 1} of {STEPS.length}
              </p>
              <h2 className="heading-fluid mt-1 truncate font-semibold tracking-tight text-slate-950 dark:text-white" id="onboarding-title">
                {current.title}
              </h2>
            </div>
          </div>

          <p className="mt-5 text-sm leading-6 text-slate-700 dark:text-slate-300">{current.body}</p>

          <ul className="mt-4 space-y-2">
            {current.highlights.map((highlight) => (
              <li className="flex items-start gap-2 text-sm leading-6 text-slate-700 dark:text-slate-300" key={highlight}>
                <ShieldCheck aria-hidden="true" className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" size={16} />
                <span className="break-words">{highlight}</span>
              </li>
            ))}
          </ul>

          {/* Progress dots */}
          <div className="mt-6 flex items-center justify-center gap-1.5">
            {STEPS.map((_, index) => (
              <button
                aria-current={index === step}
                aria-label={`Go to step ${index + 1}`}
                className={`h-2 rounded-full transition-all ${index === step ? "w-6 bg-indigo-600 dark:bg-indigo-400" : "w-2 bg-slate-300 hover:bg-slate-400 dark:bg-white/20 dark:hover:bg-white/30"}`}
                key={index}
                onClick={() => setStep(index)}
                type="button"
              />
            ))}
          </div>

          <div className="mt-6 flex flex-col-reverse items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
            <Button onClick={close} type="button" variant="secondary">
              Skip tour
            </Button>
            <div className="flex gap-2">
              <Button disabled={step === 0} onClick={() => setStep((s) => Math.max(s - 1, 0))} type="button" variant="secondary">
                <ArrowLeft size={16} /> Back
              </Button>
              {isLast ? (
                <Button onClick={close} type="button" variant="success">
                  <CheckCircle2 size={16} /> Get started
                </Button>
              ) : (
                <Button onClick={() => setStep((s) => Math.min(s + 1, STEPS.length - 1))} type="button" variant="primary">
                  Next <ArrowRight size={16} />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

/**
 * Tiny fixed-position button that re-launches the onboarding tour. Stays visible
 * after the user dismisses the modal so they can return whenever they want.
 */
function ReplayTourButton() {
  const onClick = () => window.dispatchEvent(new CustomEvent(RESTART_EVENT));
  return (
    <button
      aria-label="Replay tour"
      className="fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-700 shadow-lg shadow-slate-950/10 backdrop-blur transition hover:-translate-y-0.5 hover:border-indigo-300 hover:text-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 dark:border-white/10 dark:bg-slate-900/90 dark:text-slate-200 dark:hover:border-indigo-300/40 dark:hover:text-white"
      onClick={onClick}
      title="Replay onboarding tour"
      type="button"
    >
      <Sparkles size={14} /> Replay tour
    </button>
  );
}
