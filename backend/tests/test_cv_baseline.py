"""Guard the validated MVP bean set and labels while adding precheck metadata."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'data' / 'ultralytics'))
sys.path.insert(0, str(ROOT / 'backend'))

import cv2  # noqa: E402
from core import classify, config, segment  # noqa: E402


class CvBaseline(unittest.TestCase):
    def test_precheck_keeps_mvp_accepted_set_and_classifier_labels(self):
        model = classify.load_model(str(ROOT / 'backend/weights/best.pt'))
        expected = [('tray_real_01.jpg', 16, 3, 13), ('tray_real_02.jpg', 20, 4, 16)]
        for filename, usable, fermented, poorly in expected:
            with self.subTest(filename=filename):
                image = cv2.imread(str(ROOT / 'backend/tests/images' / filename))
                original = segment.detect_beans(image)[0]
                detailed = segment.detect_beans(image, details=True)
                self.assertEqual(len(original), usable)
                self.assertEqual([bean['bbox'] for bean in original],
                                 [bean['bbox'] for bean in detailed.beans])
                self.assertEqual(detailed.detected_count,
                                 detailed.usable_count + detailed.excluded_count)
                self.assertEqual(sum(detailed.reasons.values()), detailed.excluded_count)
                predictions = classify.classify_tray(model, detailed.beans)
                self.assertEqual(len(predictions), usable)
                self.assertEqual(sum(item['label'] == config.CLASS_NAMES[0] for item in predictions), fermented)
                self.assertEqual(sum(item['label'] == config.CLASS_NAMES[1] for item in predictions), poorly)


if __name__ == '__main__':
    unittest.main()
