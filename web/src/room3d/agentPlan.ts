// Turns a plan written by the agent (agent.run_agent -> contracts/plan.*.json) into what the renderer draws.
// The agent's items carry product_id, name, dims_in and fit {verdict, results}; rejected candidates carry only
// an id, a status and a reason, so their sizes are looked up in the catalog (data/products.json).

import type { Candidate, FitResult, Plan, PlanItem, Product, Room, Verdict } from './types'

export type AgentItem = {
  slot: string
  product_id: string
  name: string
  price_usd: number | null
  dims_in: Product['dims_in']
  image_url?: string | null
  source_url: string
  fit: { verdict: Verdict; results: FitResult[] }
  why?: string
  rejected?: { product_id: string; name: string; status: string; why: string }[]
}

export type AgentPlan = { plan_id?: string; plan_url?: string; room: Room; items: AgentItem[] }

const VERDICTS: Verdict[] = ['fits', 'unsure', 'no_fit']

export function fromAgentPlan(agent: AgentPlan, catalog: Record<string, Product>, label: string): Plan {
  const items: PlanItem[] = agent.items.map((it) => {
    const known = catalog[it.product_id]
    const product: Product = {
      ...known,
      id: it.product_id,
      name: it.name,
      category: known?.category ?? it.slot,
      price_usd: it.price_usd,
      dims_in: it.dims_in,
      source_url: it.source_url,
      image_url: it.image_url,
    }
    const others: Candidate[] = (it.rejected ?? [])
      .filter((r) => catalog[r.product_id]) // no size, nothing to draw
      .map((r) => ({
        product: catalog[r.product_id],
        // "rejected" = it fit but lost on price or budget; only fit statuses colour the outline
        fit: VERDICTS.includes(r.status as Verdict) ? (r.status as Verdict) : 'fits',
        fit_results: [],
        why: r.why,
      }))
    return { slot: it.slot, product, fit: it.fit.verdict, fit_results: it.fit.results, why: it.why ?? '', others }
  })
  return { about: label, generated_by: 'agent.run_agent', room: agent.room, items, stubbed: [] }
}
