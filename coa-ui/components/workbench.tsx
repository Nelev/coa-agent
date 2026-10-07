"use client"

import { AskBox } from "@/components/ask-box"
import { PdfViewer } from "@/components/pdf-viewer"
import { ResultCard } from "@/components/result-card"
import { TraceList } from "@/components/trace-list"
import { UploadPanel } from "@/components/upload-panel"
import { useRunEvents } from "@/hooks/use-run-events"
import type { Sample } from "@/model/Run"
import { useRunStore } from "@/store/run-store"

// The demo page: the CoA, the agent working on it, and the baseline beside it.
export function Workbench({
  samples,
  loadError,
}: {
  samples: Sample[]
  loadError?: string
}) {
  const agent = useRunStore((s) => s.agent)
  const baseline = useRunStore((s) => s.baseline)
  const error = useRunStore((s) => s.error)

  useRunEvents(agent?.id ?? null)

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      <h1 className="text-2xl font-semibold">CoA agent</h1>

      {(error || loadError) && (
        <p
          role="alert"
          className="rounded border border-red-300 bg-red-50 p-3 text-sm"
        >
          {error ?? loadError}
        </p>
      )}

      <UploadPanel samples={samples} />

      <div className="grid gap-4 lg:grid-cols-3">
        <section
          aria-label="Certificate of Analysis"
          className="lg:sticky lg:top-4 lg:self-start"
        >
          <PdfViewer pdfId={agent?.pdfId ?? null} />
        </section>

        <div className="space-y-4">
          <AskBox run={agent} />
          <TraceList phase={agent?.phase ?? null} />
        </div>

        <div className="space-y-4">
          <ResultCard
            title="Agent result"
            run={agent}
            emptyText="Upload a CoA to start."
          />
          <ResultCard
            title="Baseline result"
            run={baseline}
            emptyText="The fixed pipeline: read, normalize, check. It appears here."
          />
        </div>
      </div>
    </main>
  )
}
