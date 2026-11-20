// "Reading your room": what the scan actually contained, said plainly as each part loads.
import { useEffect, useMemo, useState } from 'react'
import { Check } from 'lucide-react'
import { motion } from 'motion/react'
import { inches } from '../lib/format'
import { useApp } from '../store'

const STEP_MS = 520

export default function ReadingCard() {
  const plan = useApp((s) => s.plan)
  const room = useApp((s) => s.room)
  const modelLabel = useApp((s) => s.modelLabel)
  const modelUrl = useApp((s) => s.modelUrl)
  const roomReady = useApp((s) => s.roomReady)
  const [waited, setWaited] = useState(false)
  const [shown, setShown] = useState(0)

  // If the scan can't be measured in a few seconds, carry on with the measurements the plan has.
  useEffect(() => {
    const t = setTimeout(() => setWaited(true), 4000)
    return () => clearTimeout(t)
  }, [])

  const steps = useMemo(() => {
    if (!plan) return []
    const out: string[] = []
    if (room) {
      const longest = room.walls.length ? Math.max(...room.walls.map((w) => w.length_in)) : 0
      out.push(modelUrl ? `Loaded ${modelLabel ?? 'the scan'}` : 'Drew the room from typed measurements')
      if (room.walls.length) out.push(`${room.walls.length} walls, the longest ${inches(longest, 1)} in`)
      const door = room.doors[0]
      if (door) out.push(`A door, ${inches(door.width_in, 1)} in wide and ${inches(door.height_in, 1)} in tall`)
      const floor = room.existing.filter((e) => e.on_floor)
      const wall = room.existing.filter((e) => !e.on_floor)
      if (floor.length || wall.length) {
        const bits = [
          floor.length ? `${floor.length} ${floor.length === 1 ? 'piece' : 'pieces'} of furniture` : '',
          wall.length ? `${wall.length === 1 ? 'a wall-mounted TV' : `${wall.length} wall-mounted items`}` : '',
        ].filter(Boolean)
        out.push(`Already in the room: ${bits.join(' and ')}`)
      }
    } else if (waited) {
      out.push(`Using the measurements on file: ${inches(plan.room.wall.value_in)} × ${inches(plan.room.depth.value_in)} in`)
    }
    return out
  }, [plan, room, waited, modelLabel, modelUrl])

  useEffect(() => {
    if (!steps.length) return
    if (shown < steps.length) {
      const t = setTimeout(() => setShown((n) => n + 1), STEP_MS)
      return () => clearTimeout(t)
    }
    const t = setTimeout(roomReady, 700)
    return () => clearTimeout(t)
  }, [steps.length, shown, roomReady])

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 380, damping: 34 }}
      className="pointer-events-none absolute inset-x-0 bottom-4 z-20 flex justify-center px-4"
    >
      <div className="glass pointer-events-auto w-full max-w-[520px] rounded-lg p-4" role="status" aria-live="polite">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-2 w-2" aria-hidden>
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-fg/50" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-fg" />
          </span>
          <h2 className="text-base font-medium text-fg">Reading your room</h2>
        </div>
        <ul className="mt-3 min-h-[5.5rem] space-y-1.5">
          {steps.slice(0, shown).map((s) => (
            <motion.li
              key={s}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
              className="flex items-center gap-2 text-sm text-fg-2"
            >
              <Check size={13} strokeWidth={2.4} className="shrink-0 text-fits" aria-hidden />
              <span className="num">{s}</span>
            </motion.li>
          ))}
          {!steps.length && <li className="text-sm text-fg-3">Opening the scan</li>}
        </ul>
      </div>
    </motion.div>
  )
}
