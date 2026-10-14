"""DFL, class rejection and original-frame coordinate regressions."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from person_rknn_v8 import decode
from person_detector import suppress_duplicates


class DecodeTest(unittest.TestCase):
    def make_heads(self):
        outputs = []
        for grid in (80,40,20):
            outputs += [np.zeros((1,64,grid,grid), np.float32), np.zeros((1,80,grid,grid), np.float32)]
        return outputs

    def test_dfl_coordinates_and_padding(self):
        heads = self.make_heads()
        heads[1][0,0,40,40] = .8
        box = decode(heads)[0]
        self.assertAlmostEqual(box['left'], (40.5-7.5)*8/640)
        self.assertAlmostEqual(box['top'], ((40.5-7.5)*8-80)/480)
        self.assertAlmostEqual(box['right'], (40.5+7.5)*8/640)
        self.assertAlmostEqual(box['bottom'], ((40.5+7.5)*8-80)/480)

    def test_other_class_and_background_rejected(self):
        heads = self.make_heads()
        self.assertEqual(decode(heads), [])
        heads[1][0,0,40,40] = .8
        heads[1][0,24,40,40] = .9
        self.assertEqual(decode(heads), [])

    def test_distinct_dfl_channels_at_two_locations(self):
        heads = self.make_heads()
        heads[0].fill(-80)
        for y,x,dist in [(40,40,(2,3,4,5)), (30,50,(5,4,3,2))]:
            heads[1][0,0,y,x] = .8
            for side,peak in enumerate(dist):
                heads[0][0,side*16+peak,y,x] = 80
        boxes = decode(heads)
        self.assertEqual(len(boxes), 2)
        for box,(y,x,dist) in zip(boxes, [(30,50,(5,4,3,2)), (40,40,(2,3,4,5))]):
            self.assertAlmostEqual(box['left'], (x+.5-dist[0])*8/640)
            self.assertAlmostEqual(box['top'], ((y+.5-dist[1])*8-80)/480)
            self.assertAlmostEqual(box['right'], (x+.5+dist[2])*8/640)
            self.assertAlmostEqual(box['bottom'], ((y+.5+dist[3])*8-80)/480)

    def test_invalid_contract_rejected(self):
        heads = self.make_heads()
        heads[1][0,0,40,40] = 2
        with self.assertRaises(ValueError): decode(heads)
        with self.assertRaises(ValueError): decode(heads[:4])

    def test_weak_near_camera_fragment_is_suppressed(self):
        person = dict(left=.1, top=.05, right=.7, bottom=1., score=.87)
        fragment = dict(left=.32, top=.34, right=.68, bottom=1., score=.48)
        self.assertEqual(suppress_duplicates([fragment,person]), [person])


if __name__ == '__main__': unittest.main()
