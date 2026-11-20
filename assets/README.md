# assets

`room_scan_geometry.glb` — the room we demo in (AWS Builder Loft, 2026-11-20), iPhone LiDAR scan, **geometry only**:
the scan's photo textures were removed because they showed people and screens. glTF 2.0, meters, Y up.
Load in R3F with `useGLTF("/room_scan_geometry.glb")`.

Measured from the scan's wall planes (2 cm bins, mid-height points): long wall 4.88 m (192 in), depth 3.42 m (135 in),
ceiling ~3.05 m. The only opening (69 x 92 in) is probably a passage, not the door: tape-measure the real door.
