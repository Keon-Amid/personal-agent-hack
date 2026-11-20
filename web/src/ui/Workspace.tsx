import { useEffect } from 'react'
import { AnimatePresence, MotionConfig } from 'motion/react'
import { useParams, useSearchParams } from 'react-router'
import RoomScene from '../scene/RoomScene'
import { demoRoomForPlan, planById } from '../data'
import { placedItems, useApp } from '../store'
import { startRun } from '../run'
import TopBar from './TopBar'
import Ledger from './Ledger'
import Inspector from './Inspector'
import CommandBar, { focusCommand } from './CommandBar'
import CartSheet from './CartSheet'
import StartScreen from './StartScreen'
import ReadingCard from './ReadingCard'
import { TipProvider } from './tooltip'

/**
 * Deep links. /plan/<id> opens a recorded plan (the agent links here).
 * For screenshots and rehearsal: ?at=ready|run|done, ?sel=<slot>, ?cam=iso|top|front, ?cart=1
 */
function useDeepLink() {
  const { id } = useParams()
  const [q] = useSearchParams()
  useEffect(() => {
    const plan = id ? planById[id] : undefined
    if (!plan) return
    const demo = demoRoomForPlan(plan.plan_id)
    useApp.getState().openRoom({ plan, modelUrl: demo?.modelUrl ?? null, modelLabel: demo?.modelLabel ?? null })
    const at = q.get('at') ?? 'done'
    if (at === 'ready') useApp.setState({ stage: 'ready' })
    if (at === 'done') useApp.getState().showAll()
    if (at === 'run') {
      useApp.setState({ stage: 'ready' })
      startRun(plan.style.style_text)
    }
    const cam = q.get('cam')
    if (cam === 'top' || cam === 'front' || cam === 'iso') useApp.getState().setCamera(cam)
    const sel = q.get('sel')
    if (sel) useApp.getState().select(sel)
    if (q.get('cart')) useApp.getState().setCartOpen(true)
    // Run once per plan id; the query string only seeds the first view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])
}

const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)

function useKeys() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useApp.getState()
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        focusCommand()
        return
      }
      if (e.key === 'Escape') {
        if (s.measuring) s.setMeasuring(null)
        else if (s.cartOpen) s.setCartOpen(false)
        else if (s.selectedSlot) s.select(null)
        else if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
        return
      }
      if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      // While a measurement is being entered, digits belong to that field wherever focus happens to be.
      if (s.measuring) {
        const field = document.getElementById(`measure-${s.measuring}`)
        if (field && (/^[0-9.]$/.test(e.key) || e.key === 'Enter')) {
          field.focus()
          if (e.key === 'Enter') {
            e.preventDefault()
            ;(field as HTMLInputElement).form?.requestSubmit()
          }
        }
        return
      }
      if (e.key === '1') s.setCamera('iso')
      if (e.key === '2') s.setCamera('top')
      if (e.key === '3') s.setCamera('front')
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        const items = placedItems(s)
        if (!items.length) return
        e.preventDefault()
        const i = items.findIndex((it) => it.slot === s.selectedSlot)
        const step = e.key === 'ArrowRight' ? 1 : -1
        const next = i === -1 ? (step === 1 ? 0 : items.length - 1) : (i + step + items.length) % items.length
        s.select(items[next].slot)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

export default function Workspace() {
  useDeepLink()
  useKeys()
  const stage = useApp((s) => s.stage)
  const selected = useApp((s) => s.selectedSlot)
  const cartOpen = useApp((s) => s.cartOpen)

  const title = useApp((s) => (s.plan ? (demoRoomForPlan(s.plan.plan_id)?.title ?? 'Your room') : null))

  return (
    <MotionConfig reducedMotion="user">
    <TipProvider>
    <div className="fixed inset-0 overflow-hidden bg-bg">
      {title && <h1 className="sr-only">Fits: {title}</h1>}
      {/* The desk the model sits on: a soft pool of light, darker toward the edges. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(90% 70% at 52% 46%, #1b1c20 0%, #101114 48%, #0c0d0f 78%)' }}
      />
      <RoomScene />

      {stage === 'start' ? (
        <StartScreen />
      ) : (
        <>
          <TopBar />
          {(stage === 'running' || stage === 'done') && <Ledger />}
          <AnimatePresence>
            {selected && !cartOpen && <Inspector key="inspector" />}
            {cartOpen && <CartSheet key="cart" />}
          </AnimatePresence>
          {stage === 'reading' ? <ReadingCard /> : <CommandBar />}
        </>
      )}
    </div>
    </TipProvider>
    </MotionConfig>
  )
}
