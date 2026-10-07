import { listSamples } from "@/api/runs"
import { Workbench } from "@/components/workbench"
import type { Sample } from "@/model/Run"

// Rendered per request: the sample list comes from the API.
export const dynamic = "force-dynamic"

export default async function Home() {
  let samples: Sample[] = []
  let loadError: string | undefined

  try {
    samples = await listSamples()
  } catch {
    loadError =
      "The API is not reachable, so the sample CoAs could not be listed."
  }

  return <Workbench samples={samples} loadError={loadError} />
}
