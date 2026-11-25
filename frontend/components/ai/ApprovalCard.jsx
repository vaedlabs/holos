// Adapted from beautifului.dev "Approval Card" (MIT, Copyright (c) 2026 Shane Levine; see LICENSE
// here): a card where the person settles something before it happens, with a quiet heading, the
// thing itself, its fields, and a footer of actions; once settled, one status line. The original's
// one-question-at-a-time wizard is left out (owner, 23 Nov 2026; D061).

export default function ApprovalCard({ eyebrow, title, meta, children, actions, status, ...props }) {
  return (
    <section data-slot="approval-card"
             className="flex flex-col overflow-hidden rounded-xl border bg-card text-card-foreground shadow-card"
             {...props}>
      <div className="flex flex-col gap-3 p-4">
        {eyebrow && (
          <p className="m-0 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{eyebrow}</p>
        )}
        {title && (
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h4 className="m-0 font-heading text-base font-semibold">{title}</h4>
            {meta && <span className="font-mono text-sm text-foreground-secondary">{meta}</span>}
          </div>
        )}
        {children}
        {status}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 border-t bg-raised/40 px-4 py-3">{actions}</div>}
    </section>
  )
}
