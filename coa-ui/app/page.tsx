// Day 4: upload panel, PDF viewer, live trace, baseline column, result card,
// answer box. The page is a Server Component; the client pieces live in
// components/.
export default function Home() {
  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="text-2xl font-semibold">CoA agent</h1>
      <p className="text-muted-foreground mt-2">
        Upload a Certificate of Analysis to start a run.
      </p>
    </main>
  )
}
