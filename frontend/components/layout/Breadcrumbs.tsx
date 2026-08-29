import Link from "next/link";

export interface Crumb {
  label: string;
  href?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="ac-breadcrumb" aria-label="Breadcrumb" style={{ marginBottom: "var(--ac-space-4)" }}>
      {items.map((item, idx) => (
        <span key={idx} className="ac-flex ac-items-center ac-gap-2">
          {idx > 0 && <span aria-hidden="true">/</span>}
          {item.href ? <Link href={item.href}>{item.label}</Link> : <span style={{ color: "var(--ac-text-primary)" }}>{item.label}</span>}
        </span>
      ))}
    </nav>
  );
}
