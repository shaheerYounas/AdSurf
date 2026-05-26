type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <div>
      {eyebrow ? <p className="text-sm font-medium uppercase tracking-wide text-slate-500">{eyebrow}</p> : null}
      <h2 className="mt-1 text-3xl font-semibold tracking-normal text-slate-950">{title}</h2>
      {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p> : null}
    </div>
  );
}

