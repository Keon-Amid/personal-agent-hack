# Room outline from a LiDAR scan (`agent/room_scan.py`)

A photo can't show a whole room. A LiDAR scan can. `room_scan.scan(bytes, name)` turns an iPhone/iPad Pro scan
(OBJ or PLY) into the floor outline, wall lengths, depth, ceiling height and open doorways. It uses the standard library only.

## Capture (about 30 s)
1. On an iPhone 12 Pro or later Pro / iPad Pro, use a free LiDAR app, e.g. **3D Scanner App** (LiDAR mode) or Polycam.
   (Untested here: check that the app's free tier exports OBJ or PLY.)
2. Open the door you'll carry furniture through. A closed door sits flush with the wall and isn't detected.
3. Walk the room slowly and **sweep every wall up to the ceiling**. The outline is traced from the strip just under the
   ceiling, above wardrobes and door frames.
4. Export **OBJ or PLY**. USDZ/GLB can't be read without extra libraries.

## Run
```
python3 -m agent.room_scan scan.obj --svg outline.svg     # JSON to stdout
```
From code: `room.estimate(scan_bytes=..., scan_name="scan.obj", photo_bytes=..., exact=...)`, where precedence
per key is exact > scan > photo > default. Values carry source `scanned:lidar` and error ±max(1 in, 2×edge spread).
The `estimate_room` audit record holds the outline, walls, doors, ceiling and method.

## Real runs (Apple ARKitScenes iPad Pro LiDAR meshes, not our room)
| Scan | Result | Time |
|---|---|---|
| 40753679 (≈1M triangles) | 4 walls, 109.8 × 143.2 in, ceiling 107.1 in, no open door | ~4 s |
| 47333462 (≈0.8M triangles) | 6 walls (L-jog), 118.7 sq ft, ceiling 102.6 in, 2 openings found | ~4 s |

These outlines were checked by eye against the scan points. ARKitScenes has no tape-measured room sizes, so **accuracy
against a tape measure is not yet shown.** Do that with our own scan: measure one wall and compare.

## Limits
- Walls are assumed to meet at right angles. A tall built-in reaching the ceiling reads as wall.
- Up axis is auto-detected (ARKit exports are y-up; ARKitScenes is z-up), and so are units (m, cm, mm).
