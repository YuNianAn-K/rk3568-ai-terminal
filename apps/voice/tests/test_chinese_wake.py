import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wake.sherpa_keyword import ChineseWakeDetector, MODEL_FILES


class ChineseWakeTests(unittest.TestCase):
    def test_missing_model_fails_without_opening_mic(self):
        capture = Mock()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                ChineseWakeDetector(directory, capture_factory=capture)
        capture.assert_not_called()

    def test_correct_local_model_and_keyword_token_configuration(self):
        sherpa = Mock()
        capture = Mock()
        with tempfile.TemporaryDirectory() as directory:
            for filename in MODEL_FILES.values():
                Path(directory, filename).write_text("x 0\niǎo 1\nài 2\nt 3\nóng 4\nué 5\n", encoding="utf-8")
            with patch.dict(sys.modules, {"sherpa_onnx": sherpa, "numpy": Mock()}):
                detector = ChineseWakeDetector(directory, capture_factory=capture)
                args = sherpa.KeywordSpotter.call_args.kwargs
                self.assertEqual(args["provider"], "cpu")
                self.assertEqual(args["num_threads"], 1)
                self.assertIn("int8", args["encoder"])
                capture.assert_not_called()
                detector.close()

    def test_exact_phrase_only_and_capture_pause_reinitializes_stream(self):
        import threading
        detector = object.__new__(ChineseWakeDetector)
        detector.lock = threading.Lock()
        detector.capture = None
        detector.stream = None
        capture = Mock()
        capture.read.return_value = b"\0\0" * 1600
        detector.capture_factory = Mock(return_value=capture)
        detector.np = Mock()
        detector.np.frombuffer.return_value.astype.return_value = 32768
        detector.model = Mock()
        for keyword, expected in (("timer", False), ("小爱", False), ("", False), ("小爱同学", True)):
            detector.model.is_ready.side_effect = [True, False]
            detector.model.get_result.return_value = keyword
            self.assertEqual(detector.poll_keyword(), expected)
        detector.model.reset_stream.assert_called_once()
        detector.pause()
        capture.close.assert_called_once()
        self.assertIsNone(detector.capture)
        self.assertIsNone(detector.stream)
        detector.model.is_ready.side_effect = [False]
        detector.poll_keyword()
        self.assertEqual(detector.capture_factory.call_count, 2)


if __name__ == "__main__": unittest.main()
