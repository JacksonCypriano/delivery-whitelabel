import type { ReactNode } from "react";

export function PageHeading({ eyebrow, title, description, actions }: {
  eyebrow?: string; title: ReactNode; description?: ReactNode; actions?: ReactNode;
}) {
  return <div className="page-heading admin-page-heading">
    <div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>
      {description && <p className="muted">{description}</p>}
    </div>
    {actions && <div className="heading-actions">{actions}</div>}
  </div>;
}
