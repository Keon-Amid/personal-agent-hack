// The page a phone opens from the QR code: pick the .glb exported from Polycam and send it to the computer.
import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Check, Upload } from 'lucide-react'
import { Wordmark } from './TopBar'

type State = { kind: 'idle' } | { kind: 'sending'; name: string; pct: number } | { kind: 'sent'; name: string } | { kind: 'error'; message: string }

export default function PhoneUpload() {
  const [q] = useSearchParams()
  const token = q.get('t') ?? ''
  const input = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<State>({ kind: 'idle' })

  const send = (file: File | undefined) => {
    if (!file) return
    if (!/\.glb$/i.test(file.name)) {
      setState({ kind: 'error', message: `${file.name} isn't a .glb. In Polycam choose Export, then GLB.` })
      return
    }
    setState({ kind: 'sending', name: file.name, pct: 0 })
    // XMLHttpRequest because it reports upload progress; fetch does not.
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/scan-upload?name=${encodeURIComponent(file.name)}&t=${encodeURIComponent(token)}`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setState({ kind: 'sending', name: file.name, pct: Math.round((e.loaded / e.total) * 100) })
    }
    xhr.onload = () => {
      if (xhr.status === 200) return setState({ kind: 'sent', name: file.name })
      let message = 'The computer did not accept the scan.'
      try {
        message = (JSON.parse(xhr.responseText) as { error?: string }).error ?? message
      } catch {
        /* keep the default */
      }
      setState({ kind: 'error', message })
    }
    xhr.onerror = () => setState({ kind: 'error', message: 'Could not reach the computer. Check that both are on the same Wi-Fi.' })
    xhr.send(file)
  }

  return (
    <main className="fixed inset-0 overflow-y-auto bg-bg px-6 py-8 text-fg">
      <Wordmark />
      <div className="mx-auto mt-12 max-w-[420px]">
        <h1 className="text-xl font-semibold leading-tight tracking-[-0.02em]">Send your room scan to the computer</h1>
        <p className="mt-3 text-base leading-relaxed text-fg-2">
          In Polycam, open the scan, tap Export and choose GLB. Save it to Files, then pick it here.
        </p>

        <input
          ref={input}
          type="file"
          accept=".glb,model/gltf-binary"
          className="sr-only"
          aria-label="Choose a room scan"
          onChange={(e) => send(e.target.files?.[0])}
        />

        {state.kind === 'sent' ? (
          <div className="glass mt-8 rounded-lg p-5" role="status">
            <p className="flex items-center gap-2 text-base font-medium">
              <Check size={18} strokeWidth={2.4} className="text-fits" aria-hidden />
              Sent
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-fg-2">
              <span className="num">{state.name}</span> is opening on the computer now. You can put the phone down.
            </p>
            <button type="button" onClick={() => setState({ kind: 'idle' })} className="btn btn-ghost mt-4 h-11 w-full text-base">
              Send a different scan
            </button>
          </div>
        ) : (
          <button
            type="button"
            disabled={state.kind === 'sending'}
            onClick={() => input.current?.click()}
            className="btn btn-primary mt-8 h-14 w-full text-base"
          >
            <Upload size={18} strokeWidth={2} aria-hidden />
            {state.kind === 'sending' ? `Sending… ${state.pct}%` : 'Choose the .glb file'}
          </button>
        )}

        {state.kind === 'sending' && (
          <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/10" aria-hidden>
            <div className="h-full rounded-full bg-fg transition-[width] duration-200" style={{ width: `${state.pct}%` }} />
          </div>
        )}
        {state.kind === 'error' && (
          <p className="mt-4 text-sm leading-relaxed text-nofit" role="alert">
            {state.message}
          </p>
        )}
        {!token && (
          <p className="mt-4 text-sm leading-relaxed text-unsure">This link is missing its code. Scan the QR code on the computer again.</p>
        )}
      </div>
    </main>
  )
}
