"""Marker positions must lie inside independently captured 2GIS parking areas."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def in_ring(point, ring):
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def in_polygon(point, rings):
    return in_ring(point, rings[0]) and not any(in_ring(point, hole) for hole in rings[1:])


class CoordinatesTests(unittest.TestCase):
    def test_all_markers_are_inside_verified_parking_surfaces(self):
        # Read configuration without importing Flask or opening the user's DB.
        tree = ast.parse((ROOT / 'app.py').read_text())
        lots = next(ast.literal_eval(n.value) for n in tree.body
                    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'LOTS' for t in n.targets))
        evidence = json.loads((ROOT / 'tests/fixtures/parking-areas.json').read_text())['parkings']
        self.assertEqual(set(lots), set(evidence))
        for key, lot in lots.items():
            with self.subTest(lot=key):
                geometry = evidence[key]['geometry']
                polygons = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
                self.assertTrue(any(in_polygon(lot['xy'], polygon) for polygon in polygons),
                                f'{key}: marker {lot["xy"]} is outside the real parking surface')


if __name__ == '__main__':
    unittest.main()
