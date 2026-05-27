type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <header className="relative overflow-hidden rounded-[2rem] border border-white/70 bg-[linear-gradient(135deg,#eef2ff_0%,#f5f3ff_42%,#ecfeff_100%)] p-6 shadow-2xl shadow-indigo-950/10 sm:p-8">
      <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-cyan-300/35 blur-3xl" />
      <div className="absolute right-40 top-12 h-56 w-56 rounded-full bg-violet-400/25 blur-3xl" />
      <div className="absolute -bottom-28 left-1/3 h-60 w-60 rounded-full bg-indigo-400/20 blur-3xl" />
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.84),rgba(255,255,255,0.62),rgba(255,255,255,0.26))]" />
      <div className="relative z-10 max-w-4xl">
        {eyebrow ? (
          <p className="inline-flex rounded-full border border-indigo-300/70 bg-white/70 px-3 py-1 text-xs font-extrabold uppercase tracking-[0.22em] text-indigo-800 shadow-sm shadow-indigo-950/5 backdrop-blur">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-4 text-4xl font-bold tracking-[-0.045em] text-[#111827] sm:text-5xl">{title}</h2>
        {description ? <p className="mt-4 max-w-3xl text-base font-semibold leading-7 text-[#334155]">{description}</p> : null}
      </div>
    </header>
  );
}
