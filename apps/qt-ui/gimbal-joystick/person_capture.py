"""Opt-in bounded, lossless diagnostic frames; never blocks inference on disk."""
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import time


class DiagnosticCapture:
    LIMIT = 40

    def __init__(self, directory, writer=None, policy=None):
        self.policy = policy or os.environ.get('PERSON_CAPTURE_POLICY', 'periodic')
        if self.policy not in ('periodic', 'events'):
            raise ValueError('unsupported person capture policy')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        existing = list(self.directory.glob('frame-*.png')) + list(self.directory.glob('frame-*.json'))
        self.count = max((int(path.stem.split('-')[1]) for path in existing), default=0)
        self.last_stamp = None
        self.previous = None
        self.event_stamp = None
        self.event_seq = None
        self.after_remaining = 0
        self.saved_seqs = set()
        self.queue = queue.Queue(maxsize=2)
        self.writer = writer or self.write_snapshot
        self.error = None
        self.closed = False
        self.thread = threading.Thread(target=self.run, name='person-capture', daemon=True)
        self.thread.start()

    def observe(self, rgb_bytes, record, stamp=None):
        stamp = time.monotonic() if stamp is None else stamp
        if self.closed or self.error or self.count >= self.LIMIT:
            return False
        if self.policy == 'events':
            return self.observe_event(rgb_bytes, record, stamp)
        interesting = len(record['raw_boxes']) != 1 or len(record['boxes']) != 1
        interval = 1.0 if interesting else 2.0
        if self.last_stamp is not None and stamp - self.last_stamp < interval:
            return False
        # Copy records: the next detector result must not mutate this pairing.
        snapshot = json.loads(json.dumps(record, allow_nan=False))
        snapshot['captured_monotonic_ms'] = round(stamp * 1000, 3)
        accepted = self.enqueue(rgb_bytes, snapshot)
        if accepted:
            self.last_stamp = stamp
        return accepted

    def enqueue(self, rgb_bytes, snapshot):
        if self.closed or self.error or self.count >= self.LIMIT:
            return False
        index = self.count + 1
        try:
            self.queue.put_nowait((index, bytes(rgb_bytes), snapshot))
        except queue.Full:
            return False
        self.count = index
        return True

    @staticmethod
    def event_reason(previous, current):
        old, new = previous['boxes'], current['boxes']
        if old and not new:
            return 'missing'
        if new and not old:
            return 'return'
        for box in old:
            matches = []
            area = (box['right'] - box['left']) * (box['bottom'] - box['top'])
            for candidate in new:
                other = ((candidate['right'] - candidate['left']) *
                         (candidate['bottom'] - candidate['top']))
                intersection = (max(0, min(box['right'], candidate['right']) -
                                    max(box['left'], candidate['left'])) *
                                max(0, min(box['bottom'], candidate['bottom']) -
                                    max(box['top'], candidate['top'])))
                union = area + other - intersection
                matches.append((intersection / union if union > 0 else 0,
                                min(area, other) / max(area, other) if max(area, other) > 0 else 0))
            best = max(matches, default=(0, 0))
            if best[0] < .25:
                return 'displacement'
            if best[1] < .50:
                return 'shape_change'
        return None

    def observe_event(self, rgb_bytes, record, stamp):
        # Keep one pre-event RGB in memory. Stable frames consume no disk
        # budget after the first reference, so later failures remain observable.
        snapshot = json.loads(json.dumps(record, allow_nan=False))
        snapshot['captured_monotonic_ms'] = round(stamp * 1000, 3)
        previous = self.previous
        current = (bytes(rgb_bytes), snapshot)
        reason = 'reference' if previous is None else self.event_reason(previous[1], snapshot)
        accepted = False

        def save(item, phase, event_seq):
            raw, data = item
            seq = data.get('seq')
            if seq is not None and seq in self.saved_seqs:
                return False
            data = dict(data, capture_policy='events', capture_phase=phase,
                        capture_event_seq=event_seq)
            saved = self.enqueue(raw, data)
            if saved and seq is not None:
                self.saved_seqs.add(seq)
            return saved

        if reason == 'reference':
            accepted = save(current, reason, snapshot.get('seq'))
        elif reason and (self.event_stamp is None or stamp - self.event_stamp >= 1.0):
            # The current failure has priority if a slow writer leaves only
            # one queue slot; context is useful but must never block inference.
            accepted = save(current, reason, snapshot.get('seq'))
            if accepted:
                self.event_stamp = stamp
                self.event_seq = snapshot.get('seq')
                self.after_remaining = 2
                save(previous, 'before', self.event_seq)
        elif self.after_remaining and snapshot['boxes']:
            # Empty results are already counted in timing logs. Reserve these
            # slots for fresh returning boxes rather than another empty scene.
            accepted = save(current, 'after', self.event_seq)
            if accepted:
                self.after_remaining -= 1
        self.previous = current if self.count < self.LIMIT else None
        return accepted

    def run(self):
        while True:
            try:
                item = self.queue.get(timeout=.1)
            except queue.Empty:
                if self.closed:
                    return
                continue
            try:
                if self.error is None:
                    self.writer(*item)
            except Exception as error:
                # Diagnostics may fail without terminating person detection.
                self.error = str(error)
            finally:
                self.queue.task_done()

    def write_snapshot(self, index, raw, record):
        import cv2
        import numpy as np
        rgb = np.frombuffer(raw, dtype=np.uint8).reshape(480, 640, 3)
        ok, encoded = cv2.imencode('.png', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                                   [cv2.IMWRITE_PNG_COMPRESSION, 1])
        if not ok:
            raise RuntimeError('diagnostic PNG encode failed')
        stem = self.directory / ('frame-%03d' % index)
        image = stem.with_suffix('.png')
        metadata = stem.with_suffix('.json')
        assert not image.exists() and not metadata.exists(), 'capture collision'
        image.write_bytes(encoded.tobytes())
        record['image'] = image.name
        record['rgb_sha256'] = hashlib.sha256(raw).hexdigest()
        metadata.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2),
                            encoding='utf-8')

    def close(self):
        self.closed = True
        self.previous = None
        # EOF occurs after the last image; drain already queued snapshots.
        self.thread.join(timeout=2)
        return self.error
