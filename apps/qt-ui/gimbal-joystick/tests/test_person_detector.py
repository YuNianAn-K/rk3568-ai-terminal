"""Model-independent regression of the person-only decoding and frame protocol."""
import io
import math
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import person_detector as detector


class PersonDetectorTest(unittest.TestCase):
    def test_filter_person_and_map_coordinates(self):
        result = detector.decode_people(
            [[.1, .2, .8, .6], [.2, .3, .9, .7], [-.1, -.2, 1.2, 1.1]],
            [0, 1, 0], [.7, .99, .8], 3)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], dict(left=0, top=0, right=1, bottom=1, score=.8))
        self.assertEqual(result[1], dict(left=.2, top=.1, right=.6, bottom=.8, score=.7))

    def test_empty_low_score_and_inverted_box(self):
        self.assertEqual(detector.decode_people([], [], [], 0), [])
        self.assertEqual(detector.decode_people([[.8, .2, .1, .4]], [0], [.9], 1), [])
        self.assertEqual(detector.decode_people([[.1, .2, .8, .9]], [0], [.54], 1), [])

    def test_invalid_result_is_rejected(self):
        for count in (-1, 11, math.nan):
            with self.assertRaises(ValueError):
                detector.decode_people([], [], [], count)
        with self.assertRaises(ValueError):
            detector.decode_people([[math.nan, 0, 1, 1]], [0], [.9], 1)
        with self.assertRaises(ValueError):
            detector.decode_people([], [], [], 1)

    def test_framing_eof_and_truncation(self):
        self.assertIsNone(detector.read_frame(io.BytesIO()))
        raw = bytes(detector.FRAME_BYTES)
        header = struct.pack("<I", len(raw))
        self.assertEqual(detector.read_frame(io.BytesIO(header + raw)), raw)
        for data in (b"\x00", struct.pack("<I", 8), header, header + b"short"):
            with self.assertRaises(ValueError):
                detector.read_frame(io.BytesIO(data))

    def test_pinned_model_and_person_label(self):
        detector.verify_model()


if __name__ == "__main__":
    unittest.main()
