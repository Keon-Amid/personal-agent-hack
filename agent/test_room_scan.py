"""Offline tests for agent.room_scan on synthetic room meshes (known geometry). Real scan: see docs/room_scan.md."""
import math
import struct
import unittest

from agent import room, room_scan

IN = room_scan.M_TO_IN
# L-shaped room, metres, CCW. Door 0.85 m wide x 2.03 m tall in the x=5 wall, y from 1.0 to 1.85.
OUTLINE = [(0, 0), (5, 0), (5, 3), (3, 3), (3, 4.2), (0, 4.2)]
CEIL = 2.4
DOOR = (1.0, 1.85, 2.03)


def quad(a, b, c, d):
    return [(a, b, c), (a, c, d)]


def room_tris():
    """Triangles (each 3 points (u, v, h)) of floor, ceiling, walls with a door opening, and a sofa box."""
    T = []
    for (x0, y0, x1, y1) in ((0, 0, 5, 3), (0, 3, 3, 4.2)):
        for h in (0.0, CEIL):
            T += quad((x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h))
    n = len(OUTLINE)
    for k in range(n):
        (ax, ay), (bx, by) = OUTLINE[k], OUTLINE[(k + 1) % n]
        if (ax, bx) == (5, 5):  # the door wall: below-door pieces either side + header above
            d0, d1, dh = DOOR
            T += quad((5, ay, 0), (5, d0, 0), (5, d0, CEIL), (5, ay, CEIL))
            T += quad((5, d1, 0), (5, by, 0), (5, by, CEIL), (5, d1, CEIL))
            T += quad((5, d0, dh), (5, d1, dh), (5, d1, CEIL), (5, d0, CEIL))
            continue
        T += quad((ax, ay, 0), (bx, by, 0), (bx, by, CEIL), (ax, ay, CEIL))
    # sofa against the y=0 wall, below the wall band
    x0, x1, y0, y1, h = 1, 3, 0.05, 0.95, 0.8
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        T += quad((*a, 0), (*b, 0), (*b, h), (*a, h))
    T += quad((x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h))
    return T


def place(p, deg=20, shift=(1.3, -0.7, 0.2)):
    """Rotate about the up axis and shift, like an arbitrary ARKit world origin."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    u, v, h = p
    return (u * c - v * s + shift[0], u * s + v * c + shift[1], h + shift[2])


def to_obj_yup():
    lines, k = [], 1
    for tri in room_tris():
        for p in tri:
            u, v, h = place(p)
            lines.append(f"v {u:.5f} {h:.5f} {v:.5f}")
        lines.append(f"f {k} {k + 1} {k + 2}")
        k += 3
    return "\n".join(lines).encode()


def to_ply_zup_cm():
    verts, faces = [], []
    for tri in room_tris():
        for p in tri:
            u, v, h = place(p)
            verts.append((u * 100, v * 100, h * 100))
        faces.append((len(verts) - 3, len(verts) - 2, len(verts) - 1))
    head = (f"ply\nformat binary_little_endian 1.0\nelement vertex {len(verts)}\nproperty float x\n"
            f"property float y\nproperty float z\nproperty uchar red\nelement face {len(faces)}\n"
            "property list uchar int vertex_indices\nend_header\n").encode()
    body = b"".join(struct.pack("<fffB", *v, 200) for v in verts)
    body += b"".join(struct.pack("<Biii", 3, *f) for f in faces)
    return head + body


def to_pointcloud_yup():
    pts = []
    for a, b, c in room_tris():
        for p in room_scan._sample_tri(a, b, c, 0.05):
            u, v, h = place(p)
            pts.append(f"v {u:.4f} {h:.4f} {v:.4f}")
    return "\n".join(pts).encode()


EXPECTED_WALLS = sorted(round(math.dist(OUTLINE[k], OUTLINE[(k + 1) % 6]) * IN, 1) for k in range(6))


class ScanTest(unittest.TestCase):
    def check(self, res, tol=0.6):
        self.assertEqual(len(res["outline_in"]), 6, res["outline_in"])
        got = sorted(w["length_in"] for w in res["walls"])
        for g, e in zip(got, EXPECTED_WALLS):
            self.assertAlmostEqual(g, e, delta=tol)
        self.assertAlmostEqual(res["area_sqft"], (15 + 3.6) * 10.7639, delta=2)
        longest = next(w for w in res["walls"] if w["id"] == res["longest_wall"])
        self.assertAlmostEqual(longest["length_in"], 5 * IN, delta=tol)
        self.assertAlmostEqual(res["depth_in"], 4.2 * IN, delta=tol)  # from the 5 m wall into the L's long arm
        self.assertAlmostEqual(res["method"]["rotation_deg"] % 90, 20, delta=0.5)

    def test_obj_yup_mesh(self):
        res = room_scan.scan(to_obj_yup(), "room.obj")
        self.check(res)
        self.assertEqual(res["method"]["up_axis"], "y")
        self.assertAlmostEqual(res["ceiling_in"], CEIL * IN, delta=0.5)
        doors = [d for d in res["doors"] if d["kind"] == "door"]
        self.assertEqual(len(doors), 1, res["doors"])
        self.assertAlmostEqual(doors[0]["width_in"], 0.85 * IN, delta=2.1)
        self.assertAlmostEqual(doors[0]["height_in"], DOOR[2] * IN, delta=1)

    def test_binary_ply_zup_centimetres(self):
        res = room_scan.scan(to_ply_zup_cm(), "room.ply")
        self.check(res)
        self.assertEqual(res["method"]["up_axis"], "z")
        self.assertEqual(res["method"]["units"], "cm")

    def test_point_cloud(self):
        res = room_scan.scan(to_pointcloud_yup(), "cloud.obj")
        self.check(res, tol=2.5)  # no normals: furniture and noise count, so looser

    def test_measurements_and_estimate(self):
        m = room_scan.to_measurements(room_scan.scan(to_obj_yup(), "room.obj"))
        self.assertEqual(m["wall"]["source"], "scanned:lidar")
        self.assertGreaterEqual(m["wall"]["error_in"], room_scan.SCAN_MIN_ERR_IN)
        rm, recs = room.estimate(scan_bytes=to_obj_yup(), scan_name="room.obj")
        self.assertAlmostEqual(rm["wall"]["value_in"], 5 * IN, delta=0.6)
        self.assertEqual(rm["door_width"]["source"], "scanned:lidar")
        rec = next(r for r in recs if r["source"]["kind"] == "lidar_scan")
        self.assertEqual(rec["step"], "estimate_room")
        self.assertEqual(len(rec["source"]["outline_in"]), 6)
        self.assertIn("scanned", rec["decision"])
        # exact values still win
        rm, _ = room.estimate(scan_bytes=to_obj_yup(), scan_name="room.obj", exact={"wall": 150})
        self.assertEqual(rm["wall"], {"value_in": 150.0, "error_in": 0.0, "source": "user"})

    def test_rejects_non_room(self):
        with self.assertRaises(room_scan.ScanError):
            room_scan.scan(b"v 0 0 0\n" * 10, "tiny.obj")
        with self.assertRaises(room_scan.ScanError):
            room_scan.scan(b"x", "room.usdz")


if __name__ == "__main__":
    unittest.main()
