import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pigeon
import youtube_upload


async def fake_tts(_text, _path):
    return [(0.0, 0.2, "hello")]


class YouTubePublishingTests(unittest.TestCase):
    def test_metadata_has_short_title_and_source_credit(self):
        title, description = youtube_upload.metadata(
            "123", "A story #Zach", "A long first sentence about a pigeon. Another sentence.")
        self.assertEqual(title, "A long first sentence about a pigeon.")
        self.assertIn("https://www.tiktok.com/@zackdfilms92/video/123", description)
        self.assertIn("#Shorts", description)

    def test_youtube_failure_keeps_tiktok_result_and_records_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (patch.object(pigeon, "WORK", Path(tmp)),
                  patch.object(pigeon, "video_info", return_value={"description": "test"}),
                  patch.object(pigeon, "is_zach", return_value=True),
                  patch.object(pigeon, "download", return_value=Path(tmp) / "source.mp4"),
                  patch.object(pigeon, "transcribe", return_value="hello"),
                  patch.object(pigeon, "tts", side_effect=fake_tts),
                  patch.object(pigeon, "render"),
                  patch.object(pigeon, "post") as tiktok,
                  patch.object(pigeon, "posting_enabled", return_value=True),
                  patch.object(youtube_upload, "configured", return_value=True),
                  patch.object(youtube_upload, "upload", side_effect=RuntimeError("quota"))):
                pigeon.YOUTUBE_FAILED = False
                try:
                    self.assertTrue(pigeon.process("123"))
                    tiktok.assert_called_once()
                    self.assertTrue(pigeon.YOUTUBE_FAILED)
                    self.assertEqual(json.loads((Path(tmp) / "youtube_status.json").read_text()),
                                     {"state": "failed", "error": "quota"})
                finally:
                    pigeon.YOUTUBE_FAILED = False


if __name__ == "__main__":
    unittest.main()
