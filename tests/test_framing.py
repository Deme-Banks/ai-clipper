import unittest

from framing import (
    blur_foreground_height,
    build_ass,
    choose_layout,
    crop_x,
    group_cues,
    smooth_track,
    source_already_fits,
    split_anchors,
    split_crop_size,
    track_crop_size,
)


def face(cx, cy=0.4, w=0.12, h=0.2):
    return {"cx": cx, "cy": cy, "w": w, "h": h}


class FramingTests(unittest.TestCase):
    def test_vertical_source_is_left_alone(self):
        self.assertTrue(source_already_fits(1080, 1920, 1080 / 1920))
        self.assertFalse(source_already_fits(1920, 1080, 1080 / 1920))

    def test_tripod_ignores_jitter_and_eases_toward_a_real_move(self):
        centers = smooth_track([0.50, 0.51, 0.505, 0.80, 0.80, 0.80])
        self.assertEqual(centers[2], 0.50)
        self.assertGreater(centers[3], 0.50)
        self.assertLess(centers[3], 0.80)
        self.assertGreater(centers[-1], centers[3])

    def test_missing_faces_hold_the_last_position(self):
        centers = smooth_track([0.3, None, None])
        self.assertEqual(centers[1], centers[0])
        self.assertEqual(centers[2], centers[0])

    def test_crop_stays_inside_the_frame(self):
        self.assertEqual(crop_x(0.0, 1920, 600), 0)
        self.assertEqual(crop_x(1.0, 1920, 600), 1320)
        self.assertEqual(crop_x(0.5, 1920, 600), 660)

    def test_two_shot_requires_both_faces_in_half_the_frames(self):
        two_shot = [[face(0.25), face(0.75)]] * 6 + [[face(0.5)]] * 2
        reverse = [[face(0.3)], [face(0.7)], [face(0.3)], [face(0.7)]]
        self.assertIsNotNone(split_anchors(two_shot))
        self.assertIsNone(split_anchors(reverse))

    def test_split_windows_do_not_contain_the_other_face(self):
        crop_w, _crop_h = split_crop_size(1920, 1080, 1080, 1920, 0.27, 0.73)
        left = crop_x(0.27, 1920, crop_w)
        right = crop_x(0.73, 1920, crop_w)
        self.assertLess(left + crop_w, int(0.73 * 1920))
        self.assertGreater(right, int(0.27 * 1920))

    def test_landscape_blur_is_taller_than_a_full_width_strip(self):
        height = blur_foreground_height(1920, 1080, 1080, 1920)
        full_width = round(1080 * 1080 / 1920)
        self.assertGreater(height, full_width)
        self.assertLessEqual(height, 1920)

    def test_portrait_blur_does_not_shrink_the_picture(self):
        height = blur_foreground_height(1080, 1920, 1080, 1920)
        self.assertEqual(height, 1920)

    def test_auto_picks_split_track_or_blur(self):
        two_shot = [[face(0.25), face(0.75)]] * 4
        one_face = [[face(0.4)]] * 4
        empty = [[] for _ in range(4)]
        self.assertEqual(choose_layout(1920, 1080, 1080, 1920, two_shot, "auto"), "split")
        self.assertEqual(choose_layout(1920, 1080, 1080, 1920, one_face, "auto"), "track")
        self.assertEqual(choose_layout(1920, 1080, 1080, 1920, empty, "auto"), "blur")
        self.assertEqual(choose_layout(1080, 1920, 1080, 1920, empty, "auto"), "fit")

    def test_track_crop_uses_the_full_height_of_a_widescreen_frame(self):
        crop_w, crop_h = track_crop_size(1920, 1080, 1080, 1920)
        self.assertEqual(crop_h, 1080)
        self.assertLess(crop_w, 1920)
        self.assertEqual(crop_w % 2, 0)

    def test_captions_group_short_cues_and_the_hook_is_in_the_script(self):
        cues = [
            {"start": 0.0, "end": 0.4, "text": "this"},
            {"start": 0.4, "end": 0.8, "text": "is"},
            {"start": 0.8, "end": 1.2, "text": "the moment"},
            {"start": 4.0, "end": 5.0, "text": "later"},
        ]
        groups = group_cues(cues)
        self.assertEqual(len(groups), 2)
        self.assertIn("moment", groups[0]["text"])
        script = build_ass(1080, 1920, "Wait for this", cues, "track", 0.45, 6)
        self.assertIn("Wait for this", script)
        self.assertIn("Style: Cap", script)
        seam = build_ass(1080, 1920, "Two people", cues, "split", 0.3, 6)
        self.assertIn("\\an5\\pos(540,960)", seam)


if __name__ == "__main__":
    unittest.main()
