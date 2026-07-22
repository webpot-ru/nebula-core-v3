import tempfile
import unittest
from subprocess import CalledProcessError
from pathlib import Path

from PIL import Image

from acc1_editorial_motion import build_editorial_motion_contract
from acc1_visual_contract import (
    ADULT_ANIMATION_WORK_STYLE_PROFILE,
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    EDITORIAL_MOTION_MODE,
    EDITORIAL_MOTION_STYLE_PROFILE,
)
from compilation_editorial_motion_renderer import (
    EditorialMotionRenderError,
    _composition_html,
    _cinematic_webtoon_scene_tweens,
    _ink_gouache_scene_tweens,
    _run,
    preflight_editorial_motion_storyboard,
)
from acc1_visual_contract import INK_GOUACHE_STORY_PAGES_STYLE_PROFILE


class EditorialMotionRendererTests(unittest.TestCase):
    def test_run_reports_stdout_and_stderr_on_cli_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(EditorialMotionRenderError) as caught:
                _run(["sh", "-c", "echo json-detail; echo browser-detail >&2; exit 1"], cwd=Path(tmp))
        self.assertIn("json-detail", str(caught.exception))
        self.assertIn("browser-detail", str(caught.exception))

    def _storyboard(
        self, root: Path, *, profile: str = EDITORIAL_MOTION_STYLE_PROFILE,
        story_family: str | None = None, page_layout: str | None = None,
    ):
        assets = []
        for index, role in enumerate(("hero_plate", "detail_plate"), start=1):
            path = root / f"{role}.png"
            Image.new("RGB", (1536, 864), f"#{index}{index}{index}922").save(path)
            import hashlib
            assets.append({
                "kind": "generated_image",
                "local_path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "asset_family_id": "pack-one",
                "layer_role": role,
                "motion_module": "living_photo_depth",
                "source_excerpt_sha256": "a" * 64,
                "factual_text_allowed": False,
                "story_family": story_family,
                "page_layout": page_layout,
            })
        text = "один два три четыре"
        contract = build_editorial_motion_contract(
            narration_segments=[{
                "segment_id": "story_one",
                "kind": "story",
                "voice_role": "narrator",
                "text": text,
            }],
            segment_timings={
                "story_one": {
                    "duration_sec": 20.0,
                    "timing_source": "ai33",
                    "words": [
                        {"word": word, "start": index * 5, "end": (index + 1) * 5}
                        for index, word in enumerate(text.split())
                    ],
                },
            },
            story_assets={"story_one": assets},
            story_metadata={"story_one": {"story_index": 1, "title": "Тест"}},
            final_audio_duration_sec=20.0,
            style_profile=profile,
        )
        return {
            "version": 4,
            "format": "compilation_16x9",
            "resolution": [1920, 1080],
            "fps": 30,
            "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": profile,
            "publication_authorized": False,
            "timeline_duration_sec": 20.0,
            "slides": contract["scenes"],
            "motion_plan": contract["motion_plan"],
            "motion_plan_sha256": contract["motion_plan"]["motion_plan_sha256"],
            "caption_track": contract["caption_track"],
            "caption_track_sha256": contract["caption_track"]["caption_track_sha256"],
        }

    def test_preflight_accepts_exact_local_asset_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checked = preflight_editorial_motion_storyboard(self._storyboard(root), root)
        self.assertEqual(len(checked), 1)
        self.assertEqual(len(checked[0]["verified_assets"]), 2)

    def test_preflight_rejects_tampered_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = self._storyboard(root)
            (root / "hero_plate.png").write_bytes(b"tampered")
            with self.assertRaisesRegex(EditorialMotionRenderError, "checksum"):
                preflight_editorial_motion_storyboard(storyboard, root)

    def test_ink_gouache_v2_uses_sparse_connectors_and_varied_typography(self):
        scene = {
            "scene_id": "story-motion-003",
            "start_sec": 82.5,
            "end_sec": 118.75,
            "duration_sec": 36.25,
            "presentation": "story",
            "story_family": "digital",
            "page_layout": "message_cascade",
            "story_title": "ПРИГЛАШЕНИЕ",
            "source_label": "РЕДАКЦИОННАЯ ИЛЛЮСТРАЦИЯ",
            "narration_text": "точный исходный фрагмент",
            "motion": {"module": "digital_memory_stack"},
            "workspace_assets": ["assets/hero.png", "assets/detail.png"],
        }
        html = _composition_html(
            [scene], 118.75, style_profile=INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
        )
        self.assertIn("Ink & Gouache v2", html)
        self.assertIn(".story-line{opacity:0", html)
        self.assertIn(".layout-message_cascade .story-line", html)
        self.assertIn(".layout-message_cascade .story-copy{left:auto;right:72px", html)
        self.assertIn(".layout-empty_desk_release .object-fragment{display:none}", html)
        self.assertIn(".plane-yellow{display:none}", html)
        self.assertNotIn('id="clip-story-motion-003"\n        data-start=', html)

        tweens = "\n".join(_ink_gouache_scene_tweens(scene))
        self.assertIn("#grade-story-motion-003", tweens)
        self.assertIn("scale:1.28", tweens)
        self.assertIn("duration:0.50", tweens)
        self.assertIn(", 82.020);", tweens)

    def test_adult_animation_profile_preflights_and_uses_its_own_comic_motion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = self._storyboard(
                root,
                profile=ADULT_ANIMATION_WORK_STYLE_PROFILE,
                story_family="adult_work",
                page_layout="office_grid_break",
            )
            checked = preflight_editorial_motion_storyboard(storyboard, root)
            html = _composition_html(
                [{**checked[0], "workspace_assets": ["assets/hero.png", "assets/detail.png"]}],
                20.0,
                style_profile=ADULT_ANIMATION_WORK_STYLE_PROFILE,
            )
        self.assertEqual(len(checked), 1)
        self.assertIn("Adult Animation v1", html)
        self.assertIn("profile-adult_animation_work_v1", html)
        self.assertIn("layout-office_grid_break", html)
        self.assertNotIn("один два три четыре", html)

    def test_cinematic_webtoon_keeps_complete_pages_and_reads_them_in_sequence(self):
        scene = {
            "scene_id": "story-motion-007",
            "start_sec": 40.0,
            "end_sec": 70.0,
            "duration_sec": 30.0,
            "presentation": "story",
            "story_family": "relationships",
            "page_layout": "evidence_slits",
            "story_title": "СЕМЕЙНЫЙ КОНФЛИКТ",
            "source_label": "РЕДАКЦИОННАЯ ИЛЛЮСТРАЦИЯ",
            "narration_text": "этот текст должен остаться только в субтитрах",
            "motion": {"module": "evidence_transform"},
            "workspace_assets": ["assets/hero.png", "assets/detail.png"],
        }
        html = _composition_html(
            [scene], 70.0, style_profile=CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
        )
        tweens = "\n".join(_cinematic_webtoon_scene_tweens(scene))
        self.assertIn("Cinematic Webtoon v2", html)
        self.assertIn("profile-cinematic_ink_webtoon_v1", html)
        self.assertIn("top:18px;bottom:18px;width:auto;height:auto", html)
        self.assertIn("object-fit:contain", html)
        self.assertIn("height:130px;background:rgba(9,11,15,.94)", html)
        self.assertIn(".object-fragment,#root.profile-cinematic_ink_webtoon_v1 .story-line", html)
        self.assertNotIn("этот текст должен остаться только в субтитрах", html)
        self.assertIn("#cutout-story-motion-007", tweens)
        self.assertIn("#portal-story-motion-007", tweens)
        self.assertIn("opacity:0,duration:.46", tweens)
        self.assertNotIn("rotation", tweens)


if __name__ == "__main__":
    unittest.main()
