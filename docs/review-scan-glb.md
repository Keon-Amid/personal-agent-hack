# Review: brendan/scan-glb vs fit.scan (alistair, 14:45)

Method: ran `agent/room_scan.scan()` from the branch on both scans in `assets/`, compared with `fit.scan.load_scan()`
on the RoomPlan scan (labelled walls/door/furniture).

## 1. Keep both readers or switch to fit.scan?
Keep both, by input type:
- **RoomPlan / Polycam Floorplan GLB** (nodes named `Wall_*`, `Door_*`, `table_*`, ...): use `fit.scan`. It gets
  exact walls, the door (32 x 97 in; `room_scan` finds no door in either file) and the existing furniture, which
  `fit.layout` needs for rearranging.
- **Raw mesh** (OBJ, PLY, unlabelled GLB): use `agent/room_scan.py`.
- Dispatch: if the GLB has any `Wall_\d+` node, call `fit.scan`; else `room_scan`.

## 2. Do the numbers match?
Within ~2 in on the main dimensions:

| | room_scan, raw mesh | room_scan, RoomPlan GLB | fit.scan (room-side faces, 1d24fb2) |
|---|---|---|---|
| Long wall | 192.6 in | 189.2 in | 190.6 in |
| Depth | 141.6 in | 141.7 in | 139.7 in |
| Notch | 48.1 x 14.3 in | 42.6 x 17.6 in | 48.5 x 18.3 in |
| Ceiling | 118.8 in | 123.5 in | — |
| Door | none found | none found | 32.0 x 96.8 in |

(fit.scan used wall centrelines until 1d24fb2, which made the room ~4 in too big; fixed.)

## 3. Anything wrong in the method?
- **The 9.2 in jog / 88.9 in wall section (w7) is probably an artifact.** It appears only in the raw-mesh run. The
  RoomPlan scan of the same room and `room_scan` on the RoomPlan file both show that long wall straight. The wall
  band is 2.1–2.94 m, so something mounted high on that wall likely read as wall. **The "KIVIK 89.75 in on an
  88.9 in section -> unsure" demo moment rests on it: tape-measure that wall before using it.**
- `docs/room_scan.md` says USDZ/GLB can't be read; the branch now reads GLB.
- Doors: neither file gives a door to `room_scan` (closed door flush with the wall, as the doc warns). The RoomPlan
  file has `Door_0` explicitly.
