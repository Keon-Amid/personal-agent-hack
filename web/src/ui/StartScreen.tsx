import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import QRCode from 'qrcode'
import { ChevronRight, Upload } from 'lucide-react'
import { motion } from 'motion/react'
import { wantsLive } from '../api/api'
import { demoRooms, planById, scanModelUrl, type DemoRoom } from '../data'
import { cn, inches, usd } from '../lib/format'
import { useApp } from '../store'
import { Wordmark } from './TopBar'

function PhoneQr() {
  const [svg, setSvg] = useState('')
  const url = `${window.location.origin}/upload`
  useEffect(() => {
    QRCode.toString(url, { type: 'svg', margin: 0, errorCorrectionLevel: 'M', color: { dark: '#eeeae3', light: '#00000000' } })
      .then(setSvg)
      .catch(() => setSvg(''))
  }, [url])
  return (
    <div className="flex items-center gap-4">
      <div
        className="h-[84px] w-[84px] shrink-0 rounded-sm bg-black/30 p-2 ring-1 ring-inset ring-line [&>svg]:h-full [&>svg]:w-full"
        role="img"
        aria-label="QR code for uploading a scan from your phone"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <div className="min-w-0">
        <div className="text-sm font-medium text-fg">Send it from your phone</div>
        <p className="mt-1 text-xs leading-relaxed text-fg-2">
          Scan the room in Polycam on an iPhone Pro, export a .glb, then point the camera here.
        </p>
        <p className="mt-1.5 flex items-start gap-1.5 text-xs leading-relaxed text-fg-3">
          <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-unsure" aria-hidden />
          Phone upload isn't connected in this build. AirDrop the file and drop it here.
        </p>
      </div>
    </div>
  )
}

function RoomRow({ room, onOpen }: { room: DemoRoom; onOpen: () => void }) {
  const plan = planById[room.planId]
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group -mx-3 flex w-[calc(100%+1.5rem)] items-center gap-3 rounded-sm px-3 py-2.5 text-left transition-colors duration-150 hover:bg-white/5"
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-fg">{room.title}</div>
        <div className="num mt-0.5 text-xs text-fg-3">
          {room.note}, {inches(plan.room.wall.value_in)} × {inches(plan.room.depth.value_in)} in
        </div>
      </div>
      <div className="num shrink-0 text-right text-xs text-fg-2">
        {plan.items.length} pieces
        <div className="text-fg-3">{usd(plan.cart.total_usd)}</div>
      </div>
      <ChevronRight size={15} className="shrink-0 text-fg-3 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-fg" aria-hidden />
    </button>
  )
}

export default function StartScreen() {
  const navigate = useNavigate()
  const openRoom = useApp((s) => s.openRoom)
  const fileRef = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const live = useApp((s) => wantsLive(s.server.ready))

  // The scanned room turns slowly on the right while you decide.
  useEffect(() => {
    useApp.setState({ modelUrl: scanModelUrl })
  }, [])

  const open = (room: DemoRoom) => {
    navigate('/')
    openRoom({ plan: planById[room.planId], modelUrl: room.modelUrl, modelLabel: room.modelLabel })
  }
  const take = (file: File | undefined) => {
    if (!file) return
    if (!/\.(glb|gltf)$/i.test(file.name)) {
      setError(`${file.name} isn't a .glb scan. Export the room as GLB from Polycam and drop that.`)
      return
    }
    setError(null)
    const scanRoom = demoRooms.find((r) => r.modelUrl)
    if (!scanRoom) return
    openRoom({ plan: planById[scanRoom.planId], modelUrl: URL.createObjectURL(file), modelLabel: file.name })
  }

  return (
    <motion.main
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="pointer-events-none absolute inset-0 z-20 overflow-y-auto"
    >
      <div className="pointer-events-auto flex min-h-full w-[min(46vw,620px)] min-w-[440px] flex-col px-[clamp(28px,5vw,72px)] py-8">
        <Wordmark />

        <div className="my-auto py-10">
          <h1 className="max-w-[15ch] text-2xl font-semibold leading-[1.08] tracking-[-0.025em] text-fg">
            Furnish a room with things that fit.
          </h1>
          <p className="mt-4 max-w-[44ch] text-base leading-relaxed text-fg-2">
            Scan the room with your phone. The agent picks real IKEA pieces, checks each one against your walls and your door, and
            shows the measurement behind every choice.
          </p>

          <div
            onDragOver={(e) => {
              e.preventDefault()
              setOver(true)
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setOver(false)
              take(e.dataTransfer.files[0])
            }}
            className={cn(
              'glass mt-8 rounded-lg p-5 transition-[box-shadow,background-color] duration-150',
              over && 'bg-ice/8 ring-1 ring-ice/60',
            )}
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-sm font-medium text-fg">Drop a room scan here</div>
                <p className="mt-1 text-xs text-fg-2">A .glb from Polycam or any LiDAR scanning app.</p>
              </div>
              <button type="button" onClick={() => fileRef.current?.click()} className="btn btn-primary shrink-0">
                <Upload size={14} strokeWidth={2} aria-hidden />
                Choose a file
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".glb,.gltf,model/gltf-binary"
                className="sr-only"
                tabIndex={-1}
                aria-label="Choose a room scan"
                onChange={(e) => take(e.target.files?.[0])}
              />
            </div>
            {error && (
              <p className="mt-3 text-xs text-nofit" role="alert">
                {error}
              </p>
            )}
            <div className="hairline my-4" />
            <PhoneQr />
          </div>

          {demoRooms.length > 0 && (
            <section className="mt-8">
              <h2 className="text-sm font-semibold text-fg">Rooms from today</h2>
              <div className="mt-1.5 divide-y divide-line border-y border-line">
                {demoRooms.map((r) => (
                  <RoomRow key={r.id} room={r} onOpen={() => open(r)} />
                ))}
              </div>
              <p className="mt-2.5 max-w-[52ch] text-xs leading-relaxed text-fg-3">
                {live
                  ? 'The agent server is up: describe a room and the agent furnishes it for real. Each room also keeps the run the team recorded for it today.'
                  : 'Each room replays the agent run the team recorded for it today. The records, measurements and checks are real; only the waiting is shortened.'}
              </p>
            </section>
          )}
        </div>
      </div>
    </motion.main>
  )
}
