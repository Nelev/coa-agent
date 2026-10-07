"use client"

import { useState } from "react"

import { answerRun } from "@/api/runs"
import type { Run } from "@/model/Run"
import { useRunStore } from "@/store/run-store"

// The agent's question (FR6). Answering resumes the run.
export function AskBox({ run }: { run: Run | null }) {
  const patchAgent = useRunStore((s) => s.patchAgent)
  const setError = useRunStore((s) => s.setError)
  const [text, setText] = useState("")
  const [busy, setBusy] = useState(false)

  if (!run || run.phase !== "waiting" || !run.pendingQuestion) return null
  const { question, options } = run.pendingQuestion

  const send = async (answer: string) => {
    if (!answer.trim() || busy) return
    setBusy(true)
    // Show the run as running at once. What it does next comes from its event
    // stream, which overwrites this; an answer's own response never does, so
    // a slow one cannot put a finished run back to "running".
    patchAgent(run.id, { phase: "running", pendingQuestion: null })
    try {
      await answerRun(run.id, answer.trim())
      setText("")
    } catch {
      patchAgent(run.id, {
        phase: "waiting",
        pendingQuestion: run.pendingQuestion,
      })
      setError("The answer could not be sent.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <section
      aria-label="The agent asks"
      className="space-y-3 rounded border border-amber-300 bg-amber-50 p-4"
    >
      <p className="font-semibold">{question}</p>

      {options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((option) => (
            <button
              key={option}
              type="button"
              disabled={busy}
              onClick={() => send(option)}
              className="bg-primary text-primary-foreground rounded px-3 py-1.5 text-sm disabled:opacity-50"
            >
              {option}
            </button>
          ))}
        </div>
      )}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          send(text)
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Your answer"
          placeholder="Or type an answer"
          maxLength={500}
          className="min-w-0 flex-1 rounded border bg-white px-2 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </section>
  )
}
