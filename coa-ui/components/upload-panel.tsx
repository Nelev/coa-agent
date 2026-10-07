"use client"

import { useState } from "react"

import { startBaseline, startRun } from "@/api/runs"
import type { Sample } from "@/model/Run"
import { useRunStore } from "@/store/run-store"

// FR1: upload a CoA, or pick one of the samples, and a run starts.
export function UploadPanel({ samples }: { samples: Sample[] }) {
  const reset = useRunStore((s) => s.reset)
  const setAgent = useRunStore((s) => s.setAgent)
  const setBaseline = useRunStore((s) => s.setBaseline)
  const setError = useRunStore((s) => s.setError)
  const [file, setFile] = useState<File | null>(null)
  const [sample, setSample] = useState("")
  const [withBaseline, setWithBaseline] = useState(true)
  const [busy, setBusy] = useState(false)

  const ready = Boolean(file || sample)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ready || busy) return
    const form = new FormData()
    if (file) form.set("file", file)
    else form.set("sample", sample)

    setBusy(true)
    reset()
    const started = await startRun(form)
    setBusy(false)

    if ("error" in started) {
      setError(started.error)
      return
    }
    setAgent(started.run)
    if (withBaseline) {
      // Not awaited: the baseline shows up when it is done, beside the agent.
      startBaseline(started.run.pdfId)
        .then(setBaseline)
        .catch(() => setError("The baseline could not be run."))
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-4 rounded border p-4"
      aria-label="Start a run"
    >
      <label className="flex flex-col gap-1 text-sm">
        Upload a CoA (PDF)
        <input
          type="file"
          accept="application/pdf"
          onChange={(e) => {
            const chosen = e.target.files?.[0] ?? null
            setFile(chosen)
            if (chosen) setSample("")
          }}
        />
      </label>

      <label className="flex flex-col gap-1 text-sm">
        or a sample
        <select
          value={sample}
          disabled={Boolean(file)}
          onChange={(e) => setSample(e.target.value)}
          className="max-w-80 rounded border bg-white px-2 py-1.5"
        >
          <option value="">Choose…</option>
          {samples.map((s) => (
            <option key={s.file} value={s.file}>
              {s.scenario}. {s.title}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={withBaseline}
          onChange={(e) => setWithBaseline(e.target.checked)}
        />
        Also run the baseline
      </label>

      <button
        type="submit"
        disabled={!ready || busy}
        className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {busy ? "Starting…" : "Run"}
      </button>
    </form>
  )
}
