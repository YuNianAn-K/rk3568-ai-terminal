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
        self.assertEqual(detector.decode_people([[.1, .2, .8, .9]], [0], [.39], 1), [])
        self.assertEqual(len(detector.decode_people([[.1, .2, .8, .9]], [0], [.54], 1)), 1)

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

    def test_duplicate_and_weak_contained_fragment(self):
        person = dict(left=.1, top=.1, right=.9, bottom=.9, score=.65)
        duplicate = dict(person, left=.12, score=.60)
        fragment = dict(left=.15, top=.2, right=.5, bottom=.7, score=.48)
        self.assertEqual(detector.suppress_duplicates([fragment, duplicate, person]), [person])

    def test_distinct_and_reliable_nested_people_remain(self):
        person = dict(left=.1, top=.1, right=.9, bottom=.9, score=.80)
        nested = dict(left=.15, top=.2, right=.5, bottom=.7, score=.70)
        separate = dict(left=0, top=0, right=.08, bottom=.8, score=.45)
        self.assertEqual(detector.suppress_duplicates([person, nested, separate]),
                         [person, nested, separate])

    def test_recorded_single_person_upper_body_duplicate(self):
        # Two outputs from the user's stationary single-person session.
        person = dict(left=.01881, top=0, right=.90642, bottom=.85948, score=.5742)
        upper = dict(left=.29573, top=0, right=.90067, bottom=.7401, score=.4883)
        self.assertEqual(detector.suppress_duplicates([person, upper]), [person])

    def test_weak_candidate_confirmation_and_misses(self):
        box = dict(left=.1, top=.1, right=.4, bottom=.9, score=.45)
        stream = detector.CandidateFilter()
        self.assertEqual(stream.update([box]), [])
        self.assertEqual(stream.update([box]), [])
        self.assertEqual(stream.update([box]), [box])
        self.assertEqual(stream.update([]), [])  # Never emit an old box.
        self.assertEqual(stream.update([box]), [box])
        for _ in range(3):
            self.assertEqual(stream.update([]), [])
        self.assertEqual(stream.update([box]), [])

    def test_confirmed_target_can_immediately_drop_score(self):
        box = dict(left=.1, top=.1, right=.4, bottom=.9, score=.60)
        stream = detector.CandidateFilter()
        self.assertEqual(stream.update([box]), [box])
        weak = dict(box, score=.43)
        self.assertEqual(stream.update([weak]), [weak])
        other = dict(weak, left=.6, right=.9)
        self.assertEqual(stream.update([other]), [])


if __name__ == "__main__":
    unittest.main()
