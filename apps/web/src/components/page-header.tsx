type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <header className="relative overflow-hidden rounded-[2rem] border border-slate-200 bg-white p-6 shadow-xl shadow-slate-950/8 sm:p-8">
      <div className="absolute inset-y-0 right-0 hidden w-1/2 bg-[radial-gradient(circle_at_70%_30%,rgba(99,102,241,0.10),transparent_34rem)] sm:block" />
      <div className="absolute inset-0 bg-gradient-to-r from-white via-white/95 to-white/70" />
      <div className="relative z-10 max-w-4xl">
        {eyebrow ? (
          <p className="inline-flex rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-extrabold uppercase tracking-[0.22em] text-indigo-800 shadow-sm shadow-indigo-950/5">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-4 text-4xl font-bold tracking-[-0.045em] text-[#0f172a] sm:text-5xl">{title}</h2>
        {description ? <p className="mt-4 max-w-3xl text-base font-semibold leading-7 text-[#334155]">{description}</p> : null}
      </div>
    </header>
  );
}
