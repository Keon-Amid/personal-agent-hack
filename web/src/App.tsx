import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router'
import Workspace from './ui/Workspace'

// kyle's renderer test page (web/src/room3d + Harness). Kept reachable so the renderer can be checked on its own.
const Harness = lazy(() => import('./HarnessPage'))

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Workspace />} />
      <Route path="/plan/:id" element={<Workspace />} />
      <Route
        path="/harness"
        element={
          <Suspense fallback={null}>
            <Harness />
          </Suspense>
        }
      />
    </Routes>
  )
}
