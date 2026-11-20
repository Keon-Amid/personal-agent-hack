import { createRoot } from 'react-dom/client'
import Harness from './Harness'
import './room3d/room3d.css'
import './harness.css'

// For now the page is the 3D renderer's test harness. The app's UI replaces <Harness /> here
// and embeds <RoomScene /> from ./room3d.
// No StrictMode: its dev-only double mount makes drei's <Html> labels log unmount warnings.
createRoot(document.getElementById('root')!).render(<Harness />)
