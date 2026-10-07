// The uploaded CoA, shown by the browser's own PDF viewer. The file is
// fetched through the app's /pdfs route, never from the API directly.
export function PdfViewer({ pdfId }: { pdfId: string | null }) {
  if (!pdfId) {
    return (
      <div className="text-muted-foreground flex h-full min-h-64 items-center justify-center rounded border border-dashed p-4 text-center text-sm">
        The CoA appears here once uploaded.
      </div>
    )
  }

  return (
    <iframe
      title="Certificate of Analysis"
      src={`/pdfs/${pdfId}`}
      className="h-[70vh] w-full rounded border"
    />
  )
}
