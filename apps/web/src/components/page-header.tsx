type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <header className="rounded-2xl border border-white/70 bg-[linear-gradient(135deg,#eef2ff_0%,#f5f3ff_48%,#ecfeff_100%)] p-5 shadow-sm sm:p-6">
      <div className="max-w-4xl">
        {eyebrow ? (
          <p className="inline-flex rounded-full border border-indigo-300/60 bg-white/80 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-indigo-700 shadow-sm backdrop-blur">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="mt-3 text-2xl font-bold tracking-tight text-[#111827] sm:text-3xl">{title}</h2>
        {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-[#475569]">{description}</p> : null}
      </div>
    </header>
  );
}