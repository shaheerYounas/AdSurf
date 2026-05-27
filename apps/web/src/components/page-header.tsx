type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <header className="relative overflow-hidden rounded-[2rem] border border-white/60 bg-white/75 p-6 shadow-xl shadow-slate-950/5 backdrop-blur-2xl dark:border-white/10 dark:bg-white/8 sm:p-8">
      <div className="absolute inset-y-0 right-0 hidden w-1/2 bg-[radial-gradient(circle_at_70%_30%,rgba(99,102,241,0.18),transparent_34rem)] sm:block" />
      <div className="relative max-w-4xl">
        {eyebrow ? (
          <p className="inline-flex rounded-full border border-indigo-200/70 bg-indigo-50/80 px-3 py-1 text-xs font-bold uppercase tracking-[0.22em] text-indigo-700 dark:border-indigo-300/20 dark:bg-indigo-300/10 dark:text-indigo-200">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-4 text-4xl font-semibold tracking-[-0.045em] text-slate-950 dark:text-white sm:text-5xl">{title}</h2>
        {description ? <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600 dark:text-slate-300">{description}</p> : null}
      </div>
    </header>
  );
}
