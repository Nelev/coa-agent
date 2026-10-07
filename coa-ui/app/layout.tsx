import "./globals.css"

import type { Metadata } from "next"

import { DemoBanner } from "@/components/demo-banner"

export const metadata: Metadata = {
  title: "CoA agent",
  description: "What an AI agent adds over a fixed CoA pipeline",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <DemoBanner />
        {children}
      </body>
    </html>
  )
}
