"""Bounded diagnostic collection is independent of model and camera/UART."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from person_capture import DiagnosticCapture


class CaptureTest(unittest.TestCase):
    def test_event_policy_keeps_late_failure_context(self):
        written = []
        box = dict(left=.1, top=.1, right=.4, bottom=.9, score=.8)
        def record(seq, boxes):
            return dict(seq=seq, raw_boxes=boxes, boxes=boxes)
        with tempfile.TemporaryDirectory() as directory:
            capture = DiagnosticCapture(directory, lambda *item: written.append(item), policy='events')
            self.assertTrue(capture.observe(b'first', record(1, [box]), 0))
            capture.queue.join()
            for seq in range(2, 601):
                self.assertFalse(capture.observe(b'stable', record(seq, [box]), seq / 7.5))
            self.assertEqual(capture.count, 1)
            self.assertTrue(capture.observe(b'miss', record(601, []), 81))
            capture.queue.join()
            self.assertFalse(capture.observe(b'next', record(602, []), 81.15))
            capture.queue.join()
            self.assertFalse(capture.observe(b'next', record(603, []), 81.30))
            capture.queue.join()
            self.assertTrue(capture.observe(b'return', record(604, [box]), 81.45))
            capture.queue.join()
            self.assertTrue(capture.observe(b'return', record(605, [box]), 81.60))
            capture.queue.join()
            self.assertFalse(capture.observe(b'next', record(606, [box]), 81.75))
            capture.close()
            records = {item[2]['seq']: item for item in written}
            self.assertEqual(set(records), {1, 600, 601, 604, 605})
            self.assertEqual(records[601][1], b'miss')
            self.assertEqual(records[600][2]['capture_phase'], 'before')
            self.assertEqual(records[604][2]['capture_event_seq'], 601)
            self.assertEqual(records[600][2]['captured_monotonic_ms'], 80000)

    def test_events_detect_foreground_jump_even_with_stable_background(self):
        background = dict(left=.01, top=.2, right=.13, bottom=.8, score=.8)
        body = dict(left=.6, top=.01, right=1., bottom=.9, score=.8)
        moved = dict(left=.3, top=.1, right=.6, bottom=.95, score=.8)
        old = dict(boxes=[body, background])
        self.assertEqual(DiagnosticCapture.event_reason(old, dict(boxes=[moved, background])), 'displacement')
        self.assertEqual(DiagnosticCapture.event_reason(old, dict(boxes=[background])), 'displacement')
        self.assertIsNone(DiagnosticCapture.event_reason(old, dict(boxes=[background, body])))
        self.assertEqual(DiagnosticCapture.event_reason(dict(boxes=[]), old), 'return')

    def test_event_writer_is_bounded_and_current_frame_has_priority(self):
        entered, release = threading.Event(), threading.Event()
        written = []
        def writer(*item):
            entered.set()
            release.wait(2)
            written.append(item)
        box = dict(left=.1, top=.1, right=.4, bottom=.9, score=.8)
        with tempfile.TemporaryDirectory() as directory:
            capture = DiagnosticCapture(directory, writer, policy='events')
            capture.observe(b'first', dict(seq=1, boxes=[box]), 0)
            self.assertTrue(entered.wait(1))
            capture.observe(b'previous', dict(seq=2, boxes=[box]), .1)
            started = time.monotonic()
            self.assertTrue(capture.observe(b'failure', dict(seq=3, boxes=[]), .2))
            self.assertFalse(capture.observe(b'later', dict(seq=4, boxes=[]), .3))
            self.assertLess(time.monotonic() - started, .2)
            self.assertEqual(capture.queue.maxsize, 2)
            self.assertEqual(capture.count, 3)
            release.set()
            capture.close()
            self.assertEqual([item[2]['seq'] for item in written], [1, 3, 2])

    def test_event_budget_and_restart_limit(self):
        written = []
        with tempfile.TemporaryDirectory() as directory:
            capture = DiagnosticCapture(directory, lambda *item: written.append(item), policy='events')
            box = dict(left=.1, top=.1, right=.4, bottom=.9, score=.8)
            for seq in range(100):
                capture.observe(b'rgb', dict(seq=seq, boxes=[box] if seq % 2 else []), seq * 1.1)
                capture.queue.join()
            capture.close()
            self.assertEqual(capture.count, 40)
            self.assertEqual(len(written), 40)
            Path(directory, 'frame-040.json').write_text('{}')
            restarted = DiagnosticCapture(directory, lambda *item: written.append(item), policy='events')
            self.assertFalse(restarted.observe(b'rgb', dict(seq=1, boxes=[box]), 200))
            restarted.close()
            self.assertEqual(len(written), 40)

    def test_interval_limit_and_restart_budget(self):
        written = []
        box = dict(left=.1, top=.1, right=.8, bottom=.9, score=.6)
        record = dict(seq=1, raw_boxes=[box], boxes=[box])
        with tempfile.TemporaryDirectory() as directory:
            capture = DiagnosticCapture(directory, lambda *item: written.append(item))
            self.assertTrue(capture.observe(b'rgb', record, 0))
            record['seq'] = 9
            self.assertFalse(capture.observe(b'rgb', record, 1))
            self.assertTrue(capture.observe(b'rgb', dict(record, boxes=[]), 1))
            capture.close()
            self.assertEqual(written[0][2]['seq'], 1)
            self.assertEqual(len(written), 2)
            Path(directory, 'frame-040.json').write_text('{}')
            capture = DiagnosticCapture(directory, lambda *item: written.append(item))
            self.assertFalse(capture.observe(b'rgb', record, 10))
            capture.close()
            self.assertEqual(len(written), 2)

    def test_actual_fortieth_frame_is_last(self):
        written = []
        with tempfile.TemporaryDirectory() as directory:
            capture = DiagnosticCapture(directory, lambda *item: written.append(item))
            for index in range(40):
                self.assertTrue(capture.observe(b'rgb', dict(raw_boxes=[], boxes=[]), index))
                capture.queue.join()
            self.assertFalse(capture.observe(b'rgb', dict(raw_boxes=[], boxes=[]), 100))
            capture.close()
            self.assertEqual([item[0] for item in written], list(range(1,41)))

    def test_busy_writer_never_blocks_submission(self):
        entered, release = threading.Event(), threading.Event()
        def writer(*item):
            entered.set()
            release.wait(2)
        with tempfile.TemporaryDirectory() as directory:
            capture = DiagnosticCapture(directory, writer)
            record = dict(raw_boxes=[], boxes=[])
            self.assertTrue(capture.observe(b'rgb', record, 0))
            self.assertTrue(entered.wait(1))
            self.assertTrue(capture.observe(b'rgb', record, 1))
            self.assertTrue(capture.observe(b'rgb', record, 2))
            self.assertFalse(capture.observe(b'rgb', record, 3))
            self.assertEqual(capture.count, 3)
            release.set()
            capture.close()

    def test_writer_error_does_not_escape_to_detector(self):
        failed = threading.Event()
        def writer(*item):
            failed.set()
            raise OSError('disk unavailable')
        with tempfile.TemporaryDirectory() as directory:
            capture = DiagnosticCapture(directory, writer)
            capture.observe(b'rgb', dict(raw_boxes=[], boxes=[]), 0)
            self.assertTrue(failed.wait(1))
            self.assertEqual(capture.close(), 'disk unavailable')
            self.assertFalse(capture.observe(b'rgb', dict(raw_boxes=[], boxes=[]), 10))


if __name__ == '__main__': unittest.main()
