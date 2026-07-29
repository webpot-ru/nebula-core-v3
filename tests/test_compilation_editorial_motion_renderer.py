import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from acc1_editorial_motion import bind_payload, build_editorial_motion_contract
from acc1_visual_contract import (
    ADULT_ANIMATION_WORK_STYLE_PROFILE,
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    EDITORIAL_MOTION_MODE,
    EDITORIAL_MOTION_STYLE_PROFILE,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    build_format_visual_system_v3_semantic_camera,
    select_format_visual_system_v3_panel_grammar,
)
from compilation_editorial_motion_renderer import (
    EditorialMotionRenderError,
    _cinematic_webtoon_scene_tweens,
    _composition_html,
    _ink_gouache_scene_tweens,
    _render_segment_plan,
    _semantic_webtoon_scene_tweens,
    _run,
    assemble_editorial_motion_segments,
    build_editorial_render_segment_plan,
    preflight_editorial_motion_storyboard,
    render_editorial_motion_compilation,
)
from acc1_visual_contract import INK_GOUACHE_STORY_PAGES_STYLE_PROFILE


class EditorialMotionRendererTests(unittest.TestCase):
    def _storyboard(
        self, root: Path, *, profile: str = EDITORIAL_MOTION_STYLE_PROFILE,
        story_family: str | None = None, page_layout: str | None = None,
    ):
        assets = []
        for index, role in enumerate(("hero_plate", "detail_plate"), start=1):
            path = root / f"{role}.png"
            Image.new("RGB", (1536, 864), f"#{index}{index}{index}922").save(path)
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
        self.assertIn("40.300", tweens)

    def test_v3_profile_uses_complete_page_renderer_skin(self):
        narration = "текст остаётся только в полосе субтитров"
        scene = {
            "scene_id": "story-motion-v3",
            "start_sec": 0.0,
            "end_sec": 20.0,
            "duration_sec": 20.0,
            "presentation": "story",
            "story_family": "relationships",
            "page_layout": "bundle_story_opener",
            "story_title": "ОТДЕЛЬНАЯ ИСТОРИЯ",
            "source_label": "РЕДАКЦИОННАЯ ИЛЛЮСТРАЦИЯ",
            "narration_text": narration,
            "motion": {"module": "living_photo_depth"},
            "workspace_assets": ["assets/hero.png", "assets/detail.png"],
            **build_format_visual_system_v3_semantic_camera(
                "bundle_hook",
                narration,
            ),
        }
        html = _composition_html(
            [scene], 20.0, style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
        )
        self.assertIn("profile-acc1_format_visual_system_v3", html)
        self.assertIn("#root.profile-acc1_format_visual_system_v3 .hero-cutout", html)
        self.assertIn("object-fit:contain", html)
        self.assertNotIn("текст остаётся только в полосе субтитров", html)
        self.assertEqual(html.count('src="assets/hero.png"'), 1)
        self.assertNotIn('src="assets/detail.png"', html)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = self._storyboard(
                root,
                profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                story_family="relationships",
                page_layout="bundle_story_opener",
            )
            checked = preflight_editorial_motion_storyboard(storyboard, root)
        self.assertEqual(checked[0]["style_profile"], FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE)

    def test_v3_preflight_accepts_reused_service_page_with_distinct_camera_passes(self):
        intro_text = " ".join(f"вступление{index}" for index in range(20))
        story_text = " ".join(f"история{index}" for index in range(20))
        grammar = select_format_visual_system_v3_panel_grammar("BUNDLE", 1, 1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = []
            for index, role in enumerate(
                ("hero_plate", "detail_plate"),
                start=1,
            ):
                path = root / f"{role}.png"
                Image.new("RGB", (1536, 1024), f"#{index}{index}{index}922").save(path)
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
                    "story_family": "relationships",
                    "page_layout": "bundle_story_opener",
                    "panel_grammar": grammar["id"],
                    "panel_count": grammar["panel_count"],
                    "panel_beat_role": grammar["beat_role"],
                })

            def timing(text: str, duration: float) -> dict:
                words = text.split()
                step = duration / len(words)
                return {
                    "duration_sec": duration,
                    "timing_source": "ai33",
                    "words": [
                        {
                            "word": word,
                            "start": index * step,
                            "end": (index + 1) * step,
                        }
                        for index, word in enumerate(words)
                    ],
                }

            contract = build_editorial_motion_contract(
                narration_segments=[
                    {
                        "segment_id": "intro",
                        "kind": "intro",
                        "voice_role": "narrator",
                        "text": intro_text,
                    },
                    {
                        "segment_id": "story_one",
                        "kind": "story",
                        "voice_role": "narrator",
                        "text": story_text,
                    },
                ],
                segment_timings={
                    "intro": timing(intro_text, 30.0),
                    "story_one": timing(story_text, 20.0),
                },
                story_assets={"story_one": assets},
                story_metadata={"story_one": {
                    "story_index": 1,
                    "format_id": "BUNDLE",
                }},
                final_audio_duration_sec=50.0,
                style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            )
            storyboard = {
                "version": 4,
                "format": "compilation_16x9",
                "resolution": [1920, 1080],
                "fps": 30,
                "visual_mode": EDITORIAL_MOTION_MODE,
                "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                "publication_authorized": False,
                "timeline_duration_sec": 50.0,
                "slides": contract["scenes"],
                "motion_plan": contract["motion_plan"],
                "motion_plan_sha256": contract["motion_plan"]["motion_plan_sha256"],
                "caption_track": contract["caption_track"],
                "caption_track_sha256": contract["caption_track"]["caption_track_sha256"],
            }
            tampered = copy.deepcopy(storyboard)
            tampered["slides"][1]["panel_grammar"] = "thread_viewpoint_mosaic"
            tampered_motion_payload = {
                key: value
                for key, value in tampered["motion_plan"].items()
                if key != "motion_plan_sha256"
            }
            tampered_motion_payload["scenes"] = tampered["slides"]
            tampered["motion_plan"] = bind_payload(
                tampered_motion_payload,
                "motion_plan_sha256",
            )
            tampered["motion_plan_sha256"] = tampered["motion_plan"][
                "motion_plan_sha256"
            ]
            with self.assertRaisesRegex(
                EditorialMotionRenderError,
                "panel grammar identity drifted",
            ):
                preflight_editorial_motion_storyboard(tampered, root)
            checked = preflight_editorial_motion_storyboard(storyboard, root)
        self.assertEqual(
            [scene["semantic_camera_pass"] for scene in checked[:2]],
            ["overview", "semantic"],
        )
        self.assertNotEqual(
            checked[0]["camera_path"],
            checked[1]["camera_path"],
        )

    def test_v3_thread_preflight_and_markup_lock_question_answer_grammar(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            story_assets = {}
            story_metadata = {}
            narration_segments = []
            segment_timings = {}
            for position, (source_id, source_role, voice_role) in enumerate(
                (
                    ("prompt", "prompt", "narrator"),
                    ("response", "response", "comment"),
                ),
                start=1,
            ):
                grammar = select_format_visual_system_v3_panel_grammar(
                    "THREAD",
                    position,
                    2,
                )
                assets = []
                for asset_index, role in enumerate(
                    ("hero_plate", "detail_plate"),
                    start=1,
                ):
                    path = root / f"{source_id}-{role}.png"
                    Image.new(
                        "RGB",
                        (1536, 864),
                        f"#{position}{asset_index}4962",
                    ).save(path)
                    import hashlib
                    assets.append({
                        "kind": "generated_image",
                        "local_path": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "asset_family_id": f"{source_id}-pack",
                        "layer_role": role,
                        "motion_module": "living_photo_depth",
                        "source_excerpt_sha256": "a" * 64,
                        "factual_text_allowed": False,
                        "story_family": "confessions",
                        "page_layout": (
                            "thread_prompt_anchor"
                            if source_role == "prompt"
                            else "thread_response_vignette"
                        ),
                        "panel_grammar": grammar["id"],
                        "panel_count": grammar["panel_count"],
                        "panel_beat_role": grammar["beat_role"],
                        "format_scene_number": position,
                        "format_scene_count": 2,
                    })
                segment_id = f"story_{source_id}"
                text = (
                    "Какой секрет вы скрывали?"
                    if source_role == "prompt"
                    else " ".join(
                        f"ответ{index}" for index in range(160)
                    )
                )
                narration_segments.append({
                    "segment_id": segment_id,
                    "kind": "story",
                    "voice_role": voice_role,
                    "text": text,
                })
                words = text.split()
                duration = 20.0 if source_role == "prompt" else 96.0
                step = duration / len(words)
                segment_timings[segment_id] = {
                    "duration_sec": duration,
                    "timing_source": "local",
                    "words": [
                        {
                            "word": word,
                            "start": index * step,
                            "end": (index + 1) * step,
                        }
                        for index, word in enumerate(words)
                    ],
                }
                story_assets[segment_id] = assets
                story_metadata[segment_id] = {
                    "story_index": position,
                    "format_id": "THREAD",
                    "format_scene_number": (
                        position if source_role == "prompt" else 14
                    ),
                    "format_scene_count": (
                        2 if source_role == "prompt" else 14
                    ),
                    "source_role": source_role,
                    "thread_response_number": (
                        1 if source_role == "response" else None
                    ),
                    "editorial_role": "confession",
                }
            contract = build_editorial_motion_contract(
                narration_segments=narration_segments,
                segment_timings=segment_timings,
                story_assets=story_assets,
                story_metadata=story_metadata,
                final_audio_duration_sec=116.0,
                style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            )
            storyboard = {
                "version": 4,
                "format": "compilation_16x9",
                "resolution": [1920, 1080],
                "fps": 30,
                "visual_mode": EDITORIAL_MOTION_MODE,
                "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                "publication_authorized": False,
                "timeline_duration_sec": 116.0,
                "slides": contract["scenes"],
                "motion_plan": contract["motion_plan"],
                "motion_plan_sha256": contract["motion_plan"]["motion_plan_sha256"],
                "caption_track": contract["caption_track"],
                "caption_track_sha256": contract["caption_track"]["caption_track_sha256"],
            }
            checked = preflight_editorial_motion_storyboard(storyboard, root)
            html = _composition_html(
                [
                    {
                        **scene,
                        "workspace_assets": [
                            f"assets/{scene['source_role']}-hero.png",
                            f"assets/{scene['source_role']}-detail.png",
                        ],
                    }
                    for scene in checked
                ],
                116.0,
                style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            )
        self.assertEqual(
            [scene["panel_grammar"] for scene in checked],
            [
                "thread_prompt_anchor",
                "thread_viewpoint_mosaic",
                "thread_viewpoint_mosaic",
            ],
        )
        self.assertIn("ВОПРОС", html)
        self.assertIn("ОТВЕТ 01", html)
        self.assertIn("format-thread", html)
        self.assertIn("family-confessions", html)

    def test_v3_semantic_tweens_follow_bound_panel_coordinates_without_pullbacks(self):
        narration = (
            "Сначала семья давит на героиню. Затем сестра плачет. "
            "Героиня отказывает. Родители возмущаются."
        )
        scene = {
            "scene_id": "story-motion-v3-semantic",
            "start_sec": 10.0,
            "end_sec": 34.0,
            "duration_sec": 24.0,
            "narration_text": narration,
            **build_format_visual_system_v3_semantic_camera(
                "bundle_escalation",
                narration,
            ),
        }
        tweens = "\n".join(_semantic_webtoon_scene_tweens(scene))
        self.assertIn("scale:1.200,x:225,y:-20", tweens)
        self.assertIn("scale:1.520,x:-480,y:265", tweens)
        self.assertIn("scale:1.520,x:-480,y:-255", tweens)
        self.assertNotIn("#portal-story-motion-v3-semantic', {scale", tweens)
        self.assertNotIn("rotation", tweens)

    def test_segment_plan_resets_local_time_without_cutting_scenes(self):
        scenes = [
            {"scene_id": "one", "start_sec": 0.0, "end_sec": 40.0, "duration_sec": 40.0},
            {"scene_id": "two", "start_sec": 40.0, "end_sec": 80.0, "duration_sec": 40.0},
            {"scene_id": "three", "start_sec": 80.0, "end_sec": 130.0, "duration_sec": 50.0},
            {"scene_id": "four", "start_sec": 130.0, "end_sec": 160.0, "duration_sec": 30.0},
        ]
        plan = _render_segment_plan(scenes, max_duration_sec=90.0)
        self.assertEqual(
            [item["scene_ids"] for item in plan],
            [["one", "two"], ["three", "four"]],
        )
        self.assertEqual(plan[1]["scenes"][0]["start_sec"], 0.0)
        self.assertEqual(plan[1]["scenes"][-1]["end_sec"], 80.0)

    def test_segment_plan_rejects_one_scene_above_render_ceiling(self):
        scenes = [{
            "scene_id": "oversized",
            "start_sec": 0.0,
            "end_sec": 121.0,
            "duration_sec": 121.0,
        }]
        with self.assertRaisesRegex(EditorialMotionRenderError, "render ceiling"):
            _render_segment_plan(scenes, max_duration_sec=120.0)

    def test_assembly_uses_full_audio_and_frame_aligned_caption_burn(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            segments = [
                root / "segment-001.mp4",
                root / "segment-002.mp4",
            ]
            for index, path in enumerate(segments, start=1):
                path.write_bytes(f"segment-{index}".encode())
            audio = root / "narration.wav"
            audio.write_bytes(b"audio")
            output = root / "final.mp4"
            caption_text = "Тестовая строка"
            caption_track = bind_payload(
                {
                    "version": 1,
                    "cues": [{
                        "start_sec": 0.0,
                        "end_sec": 10.0,
                        "text": caption_text,
                        "text_sha256": hashlib.sha256(
                            caption_text.encode("utf-8"),
                        ).hexdigest(),
                    }],
                },
                "caption_track_sha256",
            )
            scenes = [
                {
                    "scene_id": "one",
                    "start_sec": 0.0,
                    "end_sec": 5.009,
                    "duration_sec": 5.009,
                    "asset_family_id": "pack-one",
                },
                {
                    "scene_id": "two",
                    "start_sec": 5.009,
                    "end_sec": 10.018,
                    "duration_sec": 5.009,
                    "asset_family_id": "pack-two",
                },
            ]
            storyboard = {
                "timeline_duration_sec": 10.018,
                "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                "caption_track": caption_track,
                "motion_plan": {"module_usage": {"panel_read": 2}},
                "motion_plan_sha256": "a" * 64,
                "caption_track_sha256": caption_track["caption_track_sha256"],
            }

            def fake_burn(_source, _captions, final_output, **_kwargs):
                final_output.write_bytes(b"final")

            with (
                mock.patch(
                    "compilation_editorial_motion_renderer.preflight_editorial_motion_storyboard",
                    return_value=scenes,
                ),
                mock.patch(
                    "compilation_editorial_motion_renderer._probe_h264",
                    side_effect=[
                        {"duration_sec": 5.033},
                        {"duration_sec": 5.033},
                        {"duration_sec": 10.033333},
                    ],
                ),
                mock.patch(
                    "compilation_editorial_motion_renderer._run",
                    return_value=mock.Mock(stdout="", stderr=""),
                ) as run,
                mock.patch(
                    "compilation_editorial_motion_renderer.burn_captions",
                    side_effect=fake_burn,
                ) as burn,
            ):
                report = assemble_editorial_motion_segments(
                    storyboard,
                    root,
                    segments,
                    output,
                    audio=audio,
                    max_duration_sec=5.01,
                )
            mux_command = run.call_args_list[1].args[0]
            burn_kwargs = burn.call_args.kwargs
        self.assertNotIn("-shortest", mux_command)
        self.assertEqual(burn_kwargs["target_duration_sec"], 10.018)
        self.assertEqual(burn_kwargs["fps"], 30)
        self.assertEqual(report["target_frame_count"], 301)
        self.assertEqual(report["frame_aligned_duration_sec"], 10.033333)
        self.assertEqual(report["duration_delta_sec"], 0.0)
        self.assertEqual(
            report["duration_normalization"],
            "cfr_tpad_trim_exact_frame_count_before_caption_burn",
        )

    def test_v3_public_segment_plan_contains_no_materialized_asset_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = self._storyboard(
                root,
                profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                story_family="relationships",
                page_layout="bundle_story_opener",
            )
            plan = build_editorial_render_segment_plan(storyboard, root)
        self.assertEqual(plan["renderer"], "hyperframes_segmented")
        self.assertEqual(plan["segment_count"], 1)
        self.assertNotIn("scenes", plan["segments"][0])
        self.assertEqual(
            plan["segments"][0]["scene_ids"],
            ["story_one-motion-001"],
        )

    def test_direct_renderer_can_only_use_bounded_segment_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "narration.wav"
            audio.write_bytes(b"audio")
            output = root / "final.mp4"
            storyboard = {
                "timeline_duration_sec": 210.0,
                "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                "motion_plan_sha256": "a" * 64,
                "caption_track_sha256": "b" * 64,
            }
            public_plan = {
                "version": 2,
                "renderer": "hyperframes_segmented",
                "max_duration_sec": 120.0,
                "timeline_duration_sec": 210.0,
                "segment_count": 2,
                "segments": [
                    {
                        "index": 1,
                        "source_start_sec": 0.0,
                        "source_end_sec": 105.0,
                        "duration_sec": 105.0,
                        "scene_ids": ["one"],
                    },
                    {
                        "index": 2,
                        "source_start_sec": 105.0,
                        "source_end_sec": 210.0,
                        "duration_sec": 105.0,
                        "scene_ids": ["two"],
                    },
                ],
            }
            rendered_indices = []

            def fake_render(
                _storyboard,
                _root,
                segment_index,
                segment_output,
                *,
                max_duration_sec,
            ):
                rendered_indices.append((segment_index, max_duration_sec))
                segment_output.write_bytes(f"segment-{segment_index}".encode())
                return {
                    "status": "PASS",
                    "temporary_workspace_removed": True,
                }

            def fake_assemble(
                _storyboard,
                _root,
                segment_paths,
                final_output,
                *,
                audio,
                max_duration_sec,
            ):
                self.assertEqual(len(segment_paths), 2)
                self.assertEqual(max_duration_sec, 120.0)
                self.assertTrue(audio.is_file())
                final_output.write_bytes(b"final")
                return {
                    "status": "PASS",
                    "renderer": "hyperframes_segmented",
                    "segment_count": 2,
                    "segment_max_duration_sec": 120.0,
                    "segments": [
                        {"duration_sec": 105.0},
                        {"duration_sec": 105.0},
                    ],
                }

            with (
                mock.patch(
                    "compilation_editorial_motion_renderer.preflight_editorial_motion_storyboard",
                    return_value=[],
                ),
                mock.patch(
                    "compilation_editorial_motion_renderer.build_editorial_render_segment_plan",
                    return_value=public_plan,
                ),
                mock.patch(
                    "compilation_editorial_motion_renderer.render_editorial_motion_segment",
                    side_effect=fake_render,
                ),
                mock.patch(
                    "compilation_editorial_motion_renderer.assemble_editorial_motion_segments",
                    side_effect=fake_assemble,
                ),
                mock.patch(
                    "compilation_editorial_motion_renderer._probe_h264",
                    return_value={"duration_sec": 105.0},
                ),
            ):
                report = render_editorial_motion_compilation(
                    storyboard,
                    root,
                    output,
                    audio=audio,
                )
                reused_report = render_editorial_motion_compilation(
                    storyboard,
                    root,
                    output,
                    audio=audio,
                )
                checkpoint_dir = root / report["segment_checkpoint_dir"]
                self.assertTrue((checkpoint_dir / "segment-001.mp4").is_file())
                self.assertTrue((checkpoint_dir / "segment-001.json").is_file())
        self.assertEqual(rendered_indices, [(1, 120.0), (2, 120.0)])
        self.assertEqual(report["renderer"], "hyperframes_segmented")
        self.assertEqual(report["segments_rendered"], 2)
        self.assertEqual(report["segments_reused"], 0)
        self.assertEqual(reused_report["segments_rendered"], 0)
        self.assertEqual(reused_report["segments_reused"], 2)
        self.assertTrue(report["segment_checkpoints_persisted"])
        self.assertEqual(
            report["render_strategy"],
            "bounded_segments_then_assembly",
        )
        self.assertTrue(report["monolithic_browser_render_forbidden"])


if __name__ == "__main__":
    unittest.main()
