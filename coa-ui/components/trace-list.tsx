"use client"

import { useEffect, useRef } from "react"

import { TraceStep } from "@/components/trace-step"
import type { RunPhase } from "@/model/Run"
import { useRunStore } from "@/store/run-store"
import type { Step } from "@/model/Step"

const totals = (steps: Step[]) =>
  steps.reduce(
    (t, s) => ({
      calls: t.calls + (s.tool ? 1 : 0),
      tokens: t.tokens + s.tokensIn + s.tokensOut,
      ms: t.ms + s.ms,
    }),
    { calls: 0, tokens: 0, ms: 0 },
  )

// The agent's steps as they arrive, with the run's totals.
export function TraceList({ phase }: { phase: RunPhase | null }) {
  const steps = useRunStore((s) => s.steps)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" })
  }, [steps.length])

  const { calls, tokens, ms } = totals(steps)

  return (
    <section aria-label="Agent trace">
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">Agent trace</h2>
        <span className="text-muted-foreground text-xs" data-testid="totals">
          {calls} tool calls · {tokens} tokens · {(ms / 1000).toFixed(1)} s in
          tools
        </span>
      </header>

      {steps.length === 0 && (
        <p className="text-muted-foreground text-sm">
          {phase === "running" ? "Starting…" : "No run yet."}
        </p>
      )}

      <ol className="space-y-2">
        {steps.map((s) => (
          <TraceStep key={s.seq} step={s} />
        ))}
      </ol>

      {phase === "running" && steps.length > 0 && (
        <p className="text-muted-foreground mt-2 text-sm" role="status">
          Working…
        </p>
      )}
      <div ref={end} />
    </section>
  )
}
