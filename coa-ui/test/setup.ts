import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterEach, beforeEach, vi } from "vitest"

import { useRunStore } from "@/store/run-store"

beforeEach(() => {
  // The zustand store is a module singleton, so state survives between tests
  // and whichever ran first would silently decide the result of the next.
  // Replaced with the store's own initial state, actions included.
  useRunStore.setState(useRunStore.getInitialState(), true)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
