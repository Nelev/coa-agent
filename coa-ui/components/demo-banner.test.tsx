import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"

import { DemoBanner } from "@/components/demo-banner"

it("says the data is synthetic and the system is not GMP", () => {
  render(<DemoBanner />)
  expect(
    screen.getByText("Demo on synthetic data; not a GMP system"),
  ).toBeInTheDocument()
})
