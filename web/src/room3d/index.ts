// The 3D room renderer. Everything the UI needs is exported from here.
//
//   import { RoomScene } from './room3d'
//   <RoomScene room={room} items={items} selected={slot} onSelect={setSlot} />
//
// room  = the same measurements fit.options.room(...) takes (wall, depth, door_width, door_height),
//         plus optional ceiling_in, door_wall and door_offset_in for drawing.
// items = one { slot, product, fit } per slot. product is the data/products.json entry for the picked id;
//         fit is "fits" | "unsure" | "no_fit" from the fit checks. Add placement to position an item yourself.
//
// The parent element must have a size: the canvas fills it.

// Per-product 3D models are optional: web/public/models/index.json lists them (made by scripts/make_model.py),
// and any product without one is drawn as a simple shape. A plan from the agent goes through fromAgentPlan().

export { RoomScene, describe, type RoomScan } from './RoomScene'
export { fromAgentPlan, type AgentPlan, type AgentItem } from './agentPlan'
export type { ModelEntry, ModelManifest } from './Model'
export { autoLayout, footprint } from './layout'
export { fmt } from './Furniture'
export * from './types'
