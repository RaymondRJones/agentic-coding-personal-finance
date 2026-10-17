import type { ReactNode } from "react";

/** Cards are separated from the page by a soft shadow, not a border. */
export function Card({ title, description, actions, children, className = "" }: {
  title?: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl bg-surface p-5 shadow-card sm:p-6 ${className}`}>
      {(title || actions) && (
        <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-1 text-sm text-ink-2">{description}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

type Tone = "neutral" | "accent" | "good" | "warning" | "critical";

const toneClasses: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-2",
  accent: "bg-accent-soft text-accent-ink",
  good: "bg-good-soft text-good-ink",
  warning: "bg-warning-soft text-warning-ink",
  critical: "bg-critical-soft text-critical-ink",
};

/** Status never rides on color alone: badges always carry a text label (and optionally an icon). */
export function Badge({ tone = "neutral", icon, children }: { tone?: Tone; icon?: ReactNode; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${toneClasses[tone]}`}>
      {icon}
      {children}
    </span>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg bg-sunken p-0.5">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
              selected ? "bg-surface text-ink shadow-card" : "text-ink-2 hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** Label de-emphasized, value emphasized: hierarchy from weight and color, not size alone. */
export function Stat({ label, value, detail }: { label: string; value: ReactNode; detail?: ReactNode }) {
  return (
    <div>
      <p className="text-sm text-ink-2">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-ink">{value}</p>
      {detail && <p className="mt-1 text-xs text-muted">{detail}</p>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="py-10 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {children && <p className="mt-1 text-sm text-muted">{children}</p>}
    </div>
  );
}

export const ArrowUp = () => (
  <svg aria-hidden viewBox="0 0 16 16" className="size-3.5" fill="currentColor">
    <path d="M8 3.5 3.5 8l1 1L7.3 6.2V12.5h1.4V6.2L11.5 9l1-1z" />
  </svg>
);

export const ArrowDown = () => (
  <svg aria-hidden viewBox="0 0 16 16" className="size-3.5" fill="currentColor">
    <path d="M8 12.5 12.5 8l-1-1-2.8 2.8V3.5H7.3v6.3L4.5 7l-1 1z" />
  </svg>
);

export const Check = () => (
  <svg aria-hidden viewBox="0 0 16 16" className="size-3.5" fill="currentColor">
    <path d="M6.5 11.2 3.3 8l1-1 2.2 2.2 5.2-5.2 1 1z" />
  </svg>
);

export const Alert = () => (
  <svg aria-hidden viewBox="0 0 16 16" className="size-3.5" fill="currentColor">
    <path d="M8 1.5 15 14H1zm-.7 4.5v4h1.4V6zm0 5v1.4h1.4V11z" />
  </svg>
);
