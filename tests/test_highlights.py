import unittest

from highlights import dedupe_highlights, sanitize_highlights, transcript_chunks


def clip(start, end, score, title="Moment"):
    return {
        "title": title,
        "start_time": start,
        "end_time": end,
        "score": score,
        "hook_sentence": "Watch this",
        "virality_reason": "It pays off.",
    }


class HighlightTests(unittest.TestCase):
    def test_higher_score_wins_when_clips_overlap(self):
        kept = dedupe_highlights([
            clip(10, 40, 70, "weaker"),
            clip(12, 42, 91, "stronger"),
            clip(80, 110, 60, "other"),
        ])
        titles = [item["title"] for item in kept]
        self.assertIn("stronger", titles)
        self.assertNotIn("weaker", titles)
        self.assertIn("other", titles)

    def test_a_small_overlap_keeps_both(self):
        kept = dedupe_highlights([
            clip(0, 30, 80),
            clip(25, 55, 70),
        ])
        self.assertEqual(len(kept), 2)

    def test_clips_outside_the_length_window_are_dropped(self):
        cleaned = sanitize_highlights(
            [
                {"title": "ok", "start_time": 5, "end_time": 35, "score": 88, "hook_sentence": "Here", "virality_reason": "Because"},
                {"title": "tiny", "start_time": 40, "end_time": 45, "score": 99, "hook_sentence": "No", "virality_reason": "Too short"},
                {"title": "past", "start_time": 90, "end_time": 120, "score": 50, "hook_sentence": "No", "virality_reason": "Past the end"},
            ],
            duration=100,
            min_duration=15,
            max_duration=60,
        )
        self.assertEqual([item["title"] for item in cleaned], ["ok"])
        self.assertEqual(cleaned[0]["score"], 88)

    def test_a_ten_point_score_is_scaled_up(self):
        cleaned = sanitize_highlights(
            [{"title": "old", "start_time": 0, "end_time": 20, "score": 8, "hook_sentence": "Go", "virality_reason": "Yes"}],
            duration=60,
            min_duration=15,
            max_duration=60,
        )
        self.assertEqual(cleaned[0]["score"], 80)

    def test_long_videos_are_split_with_overlap(self):
        cues = [{"start": second, "end": second + 1, "text": "word"} for second in range(0, 2000, 10)]
        chunks = transcript_chunks(cues, duration=2000)
        self.assertGreater(len(chunks), 1)
        first_end = max(cue["start"] for cue in chunks[0])
        second_start = min(cue["start"] for cue in chunks[1])
        self.assertLess(second_start, first_end)

    def test_short_videos_stay_in_one_chunk(self):
        cues = [{"start": 0, "end": 2, "text": "hi"}]
        self.assertEqual(len(transcript_chunks(cues, duration=600)), 1)


if __name__ == "__main__":
    unittest.main()
