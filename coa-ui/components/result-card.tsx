import { StatusBadge } from "@/components/status-badge"
import type { Finding, Run } from "@/model/Run"

const describe = (f: Finding) =>
  f.kind === "missing"
    ? `required test missing (${f.limit})`
    : f.kind === "expired" || f.kind === "unapproved"
      ? (f.evidence ?? f.kind)
      : `${f.value ?? "unreadable"} against ${f.limit}`

// The outcome of a run: status, findings, summary and the drafted request.
export function ResultCard({
  title,
  run,
  emptyText,
}: {
  title: string
  run: Run | null
  emptyText: string
}) {
  const result = run?.result

  return (
    <section
      aria-label={title}
      className="space-y-3 rounded border p-4"
      data-testid={`result-${run?.kind ?? "none"}`}
    >
      <header className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">{title}</h2>
        {result && <StatusBadge status={result.status} />}
      </header>

      {!run && <p className="text-muted-foreground text-sm">{emptyText}</p>}
      {run && !result && (
        <p className="text-muted-foreground text-sm" role="status">
          {run.phase === "waiting"
            ? "Waiting for your answer."
            : run.phase === "error"
              ? "The run failed."
              : "Running…"}
        </p>
      )}

      {result && (
        <>
          <p className="text-sm">{result.summary}</p>

          {result.findings.length > 0 && (
            <ul className="space-y-1 text-sm" aria-label="Findings">
              {result.findings.map((f) => (
                <li
                  key={`${f.test}-${f.kind}`}
                  className="rounded bg-neutral-100 p-2"
                >
                  <span className="font-mono font-semibold">{f.test}</span>{" "}
                  <span className="text-muted-foreground">
                    {f.kind}: {describe(f)}
                  </span>
                  {f.likelyCoaError && (
                    <p className="mt-1 text-xs">
                      Likely CoA error: {f.evidence}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}

          {result.draft && (
            <div className="rounded border border-dashed p-3 text-sm">
              <p className="text-muted-foreground mb-1 text-xs uppercase">
                Draft to supplier · not sent
              </p>
              <p className="font-semibold">{result.draft.subject}</p>
              <p className="mt-1 whitespace-pre-wrap">{result.draft.body}</p>
            </div>
          )}
        </>
      )}
    </section>
  )
}
