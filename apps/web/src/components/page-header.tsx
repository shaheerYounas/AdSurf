type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <header className="rounded-2xl border border-white/70 bg-[linear-gradient(135deg,#eef2ff_0%,#f5f3ff_48%,#ecfeff_100%)] p-5 shadow-sm dark:border-white/10 dark:bg-[linear-gradient(135deg,#020617_0%,#111827_50%,#172554_100%)] dark:shadow-xl dark:shadow-slate-950/20 sm:p-6">
      <div className="max-w-4xl">
        {eyebrow ? (
          <p className="inline-flex rounded-full border border-indigo-300/60 bg-white/80 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-indigo-700 shadow-sm backdrop-blur dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-3 text-2xl font-bold tracking-tight text-[#111827] dark:text-white sm:text-3xl">{title}</h2>
        {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-[#475569] dark:text-slate-300">{description}</p> : null}
      </div>
    </header>
  );
}
