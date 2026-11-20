// The 3D renderer's own test page, at /harness. Loaded only on that route so its styles stay out of the app.
import Harness from './Harness'
import './room3d/room3d.css'
import './harness.css'

export default function HarnessPage() {
  return (
    <div style={{ position: 'fixed', inset: 0, overflow: 'auto', background: '#fff', color: '#111' }}>
      <Harness />
    </div>
  )
}
