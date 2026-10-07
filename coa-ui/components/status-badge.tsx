import type { BaselineStatus } from "@/model/Run"
import { cn } from "@/lib/utils"

// Colour is never the only signal: the status is spelled out.
const STYLES: Record<BaselineStatus, string> = {
  PASS: "bg-green-100 text-green-900 border-green-300",
  REVIEW: "bg-amber-100 text-amber-900 border-amber-300",
  FAIL: "bg-red-100 text-red-900 border-red-300",
  ERROR: "bg-neutral-200 text-neutral-900 border-neutral-400",
}

export function StatusBadge({ status }: { status: BaselineStatus }) {
  return (
    <span
      data-testid="status"
      className={cn(
        "inline-block rounded border px-2 py-0.5 text-sm font-semibold",
        STYLES[status],
      )}
    >
      {status}
    </span>
  )
}
