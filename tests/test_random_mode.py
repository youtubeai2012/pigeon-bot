import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pigeon


class RandomModeTests(unittest.TestCase):
    def test_failed_post_does_not_consume_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            used = Path(tmp) / "used.json"
            seen = Path(tmp) / "seen.json"
            with (
                patch.object(pigeon, "USED", used),
                patch.object(pigeon, "STATE", seen),
                patch.object(pigeon, "latest_videos", return_value=["123"]),
                patch.object(pigeon.random, "shuffle"),
                patch.object(pigeon, "process", side_effect=RuntimeError("upload failed")),
            ):
                with self.assertRaisesRegex(RuntimeError, "upload failed"):
                    pigeon.random_mode()
            self.assertFalse(used.exists())
            self.assertFalse(seen.exists())

    def test_success_marks_video_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            used = Path(tmp) / "used.json"
            seen = Path(tmp) / "seen.json"
            with (
                patch.object(pigeon, "USED", used),
                patch.object(pigeon, "STATE", seen),
                patch.object(pigeon, "latest_videos", return_value=["123"]),
                patch.object(pigeon.random, "shuffle"),
                patch.object(pigeon, "process", return_value=True),
            ):
                pigeon.random_mode()
            self.assertEqual(pigeon.load(used), {"123"})
            self.assertEqual(pigeon.load(seen), {"123"})


if __name__ == "__main__":
    unittest.main()
