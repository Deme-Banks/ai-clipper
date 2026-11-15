import unittest

from sources import interpret_cli_window, live_capture_plan, pick_subtitle_tracks, video_source


class VideoSourceTests(unittest.TestCase):
    def test_youtube_links(self):
        self.assertEqual(video_source("https://www.youtube.com/watch?v=abc"), "YouTube")
        self.assertEqual(video_source("https://youtu.be/abc"), "YouTube")
        self.assertEqual(video_source("https://www.youtube.com/shorts/abc"), "YouTube")
        self.assertEqual(video_source("https://www.youtube.com/live/abc"), "YouTube")
        self.assertEqual(video_source("https://www.youtube-nocookie.com/embed/abc"), "YouTube")

    def test_twitch_links(self):
        self.assertEqual(video_source("https://www.twitch.tv/videos/123456"), "Twitch")
        self.assertEqual(video_source("https://clips.twitch.tv/SomeSlug"), "Twitch")
        self.assertEqual(video_source("https://www.twitch.tv/name/clip/SomeSlug"), "Twitch")

    def test_other_links_are_rejected(self):
        self.assertIsNone(video_source("https://vimeo.com/1"))
        self.assertIsNone(video_source("not a url"))
        self.assertIsNone(video_source(""))

    def test_live_window_is_bounded_and_not_rejected(self):
        plan = live_capture_plan({"is_live": True, "duration": 5 * 3600}, 180)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["seconds"], 180)
        self.assertEqual(plan["seek"], 5 * 3600 - 180)
        self.assertTrue(plan["dvr"])

    def test_live_without_dvr_starts_at_the_edge(self):
        plan = live_capture_plan({"live_status": "is_live", "duration": None}, None)
        self.assertEqual(plan["seconds"], 180)
        self.assertIsNone(plan["seek"])

    def test_live_window_cannot_exceed_ten_minutes(self):
        plan = live_capture_plan({"is_live": True}, 99999)
        self.assertEqual(plan["seconds"], 600)

    def test_finished_video_is_not_a_live_capture(self):
        self.assertIsNone(live_capture_plan({"is_live": False, "duration": 600}, 180))

    def test_cli_window_accepts_minutes_or_seconds(self):
        self.assertEqual(interpret_cli_window("3"), 180)
        self.assertEqual(interpret_cli_window("3m"), 180)
        self.assertEqual(interpret_cli_window("180"), 180)
        self.assertEqual(interpret_cli_window("20m"), 600)
        self.assertEqual(interpret_cli_window(None), 180)

    def test_english_captions_are_preferred(self):
        info = {
            "subtitles": {"es": [{"ext": "vtt"}]},
            "automatic_captions": {"en": [{"ext": "json3"}], "fr": [{"ext": "vtt"}]},
        }
        self.assertEqual(pick_subtitle_tracks(info)[0]["ext"], "json3")


if __name__ == "__main__":
    unittest.main()
