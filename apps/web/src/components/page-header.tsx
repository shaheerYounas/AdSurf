type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <header className="relative overflow-hidden rounded-2xl border border-white/70 bg-[linear-gradient(135deg,#eef2ff_0%,#f5f3ff_48%,#ecfeff_100%)] p-5 shadow-sm dark:border-white/10 dark:bg-[linear-gradient(135deg,#020617_0%,#111827_50%,#172554_100%)] dark:shadow-xl dark:shadow-slate-950/20 sm:p-6">
      {/* Decorative orbs */}
      <div aria-hidden="true" className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-indigo-400/10 blur-2xl dark:bg-indigo-400/8" />
      <div aria-hidden="true" className="pointer-events-none absolute -bottom-8 right-32 h-32 w-32 rounded-full bg-violet-400/10 blur-xl dark:bg-violet-400/8" />
      <div className="relative max-w-4xl">
        {eyebrow ? (
          <p className="inline-flex items-center gap-1.5 rounded-full border border-indigo-300/60 bg-white/80 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-indigo-700 shadow-sm backdrop-blur dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
            <span aria-hidden="true" className="status-dot-live h-1.5 w-1.5 rounded-full bg-indigo-500 dark:bg-indigo-300" />
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-3 text-2xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-3xl">
          {title}
        </h2>
        {description ? (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500 dark:text-slate-300">
            {description}
          </p>
        ) : null}
      </div>
    </header>
  );
}
