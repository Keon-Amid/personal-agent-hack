// Tooltip for icon-only controls. shadcn/ui's tooltip (Radix), restyled with this app's tokens.
import type { ReactElement, ReactNode } from 'react'
import { Tooltip as T } from 'radix-ui'
import { Kbd } from './bits'

export function TipProvider({ children }: { children: ReactNode }) {
  return (
    <T.Provider delayDuration={350} skipDelayDuration={250}>
      {children}
    </T.Provider>
  )
}

export function Tip({
  label,
  keys,
  side = 'bottom',
  children,
}: {
  label: ReactNode
  keys?: string[]
  side?: 'top' | 'bottom' | 'left' | 'right'
  children: ReactElement
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={8}
          collisionPadding={10}
          className="tip glass-solid z-50 flex max-w-[280px] items-center gap-2 rounded-sm px-2.5 py-1.5 text-xs leading-snug text-fg"
        >
          <span>{label}</span>
          {keys?.map((k) => (
            <Kbd key={k} className="h-4 min-w-4 shrink-0 px-1">
              {k}
            </Kbd>
          ))}
        </T.Content>
      </T.Portal>
    </T.Root>
  )
}
