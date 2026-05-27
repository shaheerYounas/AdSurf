type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <header className="relative overflow-hidden rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-xl shadow-slate-950/6 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/78 sm:p-8">
      <div className="absolute inset-y-0 right-0 hidden w-1/2 bg-[radial-gradient(circle_at_70%_30%,rgba(99,102,241,0.16),transparent_34rem)] sm:block" />
      <div className="absolute inset-0 bg-gradient-to-r from-white/80 via-white/58 to-transparent dark:from-slate-900/88 dark:via-slate-900/62 dark:to-transparent" />
      <div className="relative max-w-4xl">
        {eyebrow ? (
          <p className="inline-flex rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-bold uppercase tracking-[0.22em] text-indigo-700 shadow-sm shadow-indigo-950/5 dark:border-indigo-300/25 dark:bg-indigo-300/15 dark:text-indigo-100">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-4 text-4xl font-semibold tracking-[-0.045em] text-slate-950 dark:text-white sm:text-5xl">{title}</h2>
        {description ? <p className="mt-4 max-w-3xl text-base font-medium leading-7 text-slate-700 dark:text-slate-200">{description}</p> : null}
      </div>
    </header>
  );
}
