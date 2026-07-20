#!/usr/bin/env python3
"""Build a 300-second silent Reddit story pilot in contemporary_cutup_v1.

The pilot is source-locked, uses eight paired image packs, disables provider
retries, and never authorizes publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_editorial_motion import build_editorial_motion_contract
from acc1_episode_images import generate_episode_images, image_plan
from acc1_visual_contract import (
    EDITORIAL_MOTION_MODE,
    EDITORIAL_MOTION_STYLE_PROFILE,
    EDITORIAL_MOTION_STYLE_PROFILES,
)
from compilation_editorial_motion_renderer import render_editorial_motion_compilation
from vectorengine_client import DEFAULT_IMAGE_MODEL, call_image_generation, load_dotenv_file


SOURCE = {
    "source_id": "1i8nufm",
    "post_id": "1i8nufm",
    "subreddit": "BestofRedditorUpdates",
    "title": "AITAH - my coworker got fired because of me",
    "url": "https://www.reddit.com/r/BestofRedditorUpdates/comments/1i8nufm/",
    "original_subreddit": "AITAH",
    "original_author": "consistent_naz1",
    "original_post_date": "2025-01-16",
    "update_date": "2025-01-17",
    "retrieved_for_pilot": "2026-07-18",
    "adaptation_note": (
        "Russian source-faithful visual adaptation for a local silent pilot; "
        "not a verbatim republication and not publication-authorized."
    ),
}

BEATS = [
    {
        "title": "НОВАЯ РАБОТА",
        "text": (
            "Тридцатитрёхлетняя автор недавно пришла в новую компанию, быстро освоилась, "
            "подружилась с коллегами и спокойно общалась со старшим сотрудником, который "
            "рассказывал о жене и четырёх дочерях, поэтому его внимание казалось безопасным, "
            "обычным и совершенно профессиональным, а номер телефона и подписка в социальной "
            "сети не выглядели для неё тревожным знаком, ведь в первые недели она старалась "
            "быть открытой со всей командой и не видела причины заранее искать скрытый мотив "
            "в дружелюбии человека, который постоянно подчёркивал, что у него есть большая семья"
        ),
    },
    {
        "title": "СТРАННЫЙ КОНТАКТ",
        "text": (
            "Неожиданное сообщение пришло от незнакомой женщины, на фотографии профиля "
            "она узнала коллегу рядом с его женой, но решила, что ролик отправлен случайно, "
            "ничего не ответила и закрыла экран, хотя этот маленький цифровой контакт впервые "
            "связал обычный офис с личной жизнью человека, которого она знала только по работе, "
            "и оставил странный визуальный след: семейный снимок, входящий ролик без объяснения "
            "и вопрос, почему жена коллеги вообще нашла её профиль среди множества других аккаунтов"
        ),
    },
    {
        "title": "ПРИГЛАШЕНИЕ",
        "text": (
            "Затем коллега начал присылать сообщения с предложением готовить для неё в обмен "
            "на уроки её языка, она вежливо отказалась и посоветовала найти преподавателя, "
            "последующие реплики оставила без ответа, после чего он удалил их в мессенджере, "
            "сам назвал своё поведение навязчивым и извинился, а она ограничила общение коротким "
            "приветствием, не желая превращать неловкость в публичный конфликт и надеясь, что ясный "
            "отказ, молчание и его собственное признание остановят дальнейшее сближение без участия начальства"
        ),
    },
    {
        "title": "ГРАНИЦА НАРУШЕНА",
        "text": (
            "На следующий рабочий день она попыталась пройти мимо него после приветствия, "
            "но он коснулся её сзади листами бумаги, она замерла от неожиданности, не стала "
            "устраивать сцену перед людьми и ушла после смены, однако дома прежние эпизоды "
            "сложились в одну последовательность и случайностью произошедшее уже не казалось, "
            "потому что прикосновение последовало после отклонённого приглашения, удалённых реплик "
            "и извинения, а сам мужчина не остановился, чтобы немедленно объяснить ошибку или попросить прощения"
        ),
    },
    {
        "title": "РАЗГОВОР С HR",
        "text": (
            "Она подготовила письменное обращение в HR и рассказала о случившемся, компания "
            "быстро прекратила работу коллеги, а он заявил, что она лжёт, грозил судом и "
            "объяснял прикосновение попыткой переложить бумаги, из-за чего автор начала сомневаться, "
            "не следовало ли сначала предупредить его самой, как советовал другой сотрудник, "
            "хотя именно работодатель располагал полной историей, мог проверить прежние жалобы и "
            "самостоятельно выбрал увольнение, не перекладывая оценку профессионального риска на нового работника"
        ),
    },
    {
        "title": "ПОСЛЕ УВОЛЬНЕНИЯ",
        "text": (
            "Уволенный мужчина поехал в соседний рабочий корпус, где после смены коллеги "
            "иногда собирались вместе, и там изложил собственную версию, превращая приватный "
            "конфликт в слух, который должен был вернуться в главный офис уже без контроля "
            "автора, пока она ещё переживала из-за его семьи и возможных последствий увольнения, "
            "а неформальная обстановка с разговорами после работы дала его рассказу аудиторию, "
            "которая не присутствовала при исходном эпизоде, не видела переписку и слышала только одну сторону"
        ),
    },
    {
        "title": "ДРУГАЯ ВЕРСИЯ",
        "text": (
            "По его словам, она якобы сама пришла в тот корпус, где прежде никогда не бывала, "
            "и домогалась его после ухода остальных, руководитель сразу поддержал сотрудницу, "
            "а расположение помещений и возможная камера превращали придуманную встречу в "
            "проверяемое утверждение, но часть коллектива всё равно успела услышать обвинение и "
            "усомниться, поэтому история сменила масштаб: теперь речь шла не только о нарушенной "
            "границе, а о попытке заранее лишить заявительницу доверия и представить виновником именно её"
        ),
    },
    {
        "title": "НЕ ЕЁ ВИНА",
        "text": (
            "Когда история стала известна шире, автор боялась, что мужчины в компании перестанут "
            "разговаривать с ней, однако поддержка руководителя и реакция читателей помогли отделить "
            "её жалобу от решения работодателя, потому что последствия создали поступки самого "
            "коллеги и его ложная ответная версия, а не человек, который сообщил о нарушенной "
            "границе, и финальный пустой стол в этой истории означает не месть, а решение компании "
            "защитить рабочую среду после того, как прежняя вежливость и дистанция проблему не остановили"
        ),
    },
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timing(text: str, duration: float) -> dict:
    words = text.split()
    return {
        "duration_sec": duration,
        "timing_source": "silent_visual_pilot",
        "words": [
            {
                "word": word,
                "start": round(index * duration / len(words), 3),
                "end": round((index + 1) * duration / len(words), 3),
                "timing_source": "silent_visual_pilot",
            }
            for index, word in enumerate(words)
        ],
    }


def _script(style_profile: str = EDITORIAL_MOTION_STYLE_PROFILE) -> dict:
    narration = ". ".join(beat["text"] for beat in BEATS) + "."
    return {
        "episode_format": "SAGA",
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": style_profile,
        "stories": [{
            "title_ru": "КОЛЛЕГА ПОТЕРЯЛ РАБОТУ ИЗ-ЗА МЕНЯ?",
            "narration_ru": narration,
            "source_snapshot": SOURCE,
            "visual_identity_contract": (
                "Recurring illustrated author: a 33-year-old woman with an angular oval face, "
                "dark brown hair in the same practical loose bun, olive office blouse and charcoal "
                "trousers. Recurring illustrated coworker: the same adult man in every chapter, "
                "salt-and-pepper hair, short salt-and-pepper beard, deep forest-green sweater over "
                "a pale shirt. His family-profile image must show this exact same man beside the same "
                "adult wife with shoulder-length auburn-brown hair; daughters may remain background "
                "silhouettes. These are stable editorial-illustration identities, not real portraits"
            ),
            "editorial_motion_modules": [
                "living_photo_depth",
                "digital_memory_stack",
                "digital_memory_stack",
                "graphic_timeline",
                "evidence_transform",
                "nested_collage_zoom",
                "evidence_transform",
                "dark_semantic_reveal",
            ],
            "editorial_motion_families": [
                "work",
                "digital",
                "digital",
                "work",
                "work",
                "dark_saga",
                "dark_saga",
                "work",
            ],
            "editorial_page_layouts": [
                "hero_left_details_right",
                "phone_portal_insets",
                "message_cascade",
                "vertical_routine_triptych",
                "evidence_slits",
                "rumor_table_wide",
                "corridor_false_claim",
                "empty_desk_release",
            ],
        }],
    }


def _contact_sheet(video: Path, output_dir: Path) -> Path:
    frame_dir = output_dir / "review-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    times = (4, 24, 58, 92, 126, 160, 194, 232, 262, 294)
    paths: list[Path] = []
    for index, second in enumerate(times, start=1):
        path = frame_dir / f"frame-{index:02d}.png"
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(second), "-i", str(video),
                "-frames:v", "1", "-vf", "scale=640:360", str(path),
            ],
            check=True,
            capture_output=True,
        )
        paths.append(path)
    sheet = Image.new("RGB", (1280, 1800), "#111820")
    for index, path in enumerate(paths):
        with Image.open(path) as frame:
            sheet.paste(frame.convert("RGB"), ((index % 2) * 640, (index // 2) * 360))
    result = output_dir / "contact-sheet.png"
    sheet.save(result, format="PNG", optimize=True)
    return result


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(args: argparse.Namespace) -> dict:
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    style_profile = str(
        getattr(args, "style_profile", EDITORIAL_MOTION_STYLE_PROFILE),
    ).strip()
    if style_profile not in EDITORIAL_MOTION_STYLE_PROFILES:
        raise RuntimeError("unsupported editorial motion style profile")
    script = _script(style_profile)
    plan = image_plan(
        script, visual_mode=EDITORIAL_MOTION_MODE, style_profile=style_profile,
    )
    if len(plan) != 16:
        raise RuntimeError(f"pilot must use exactly 16 image attempts, planned {len(plan)}")
    dry_run = {
        "status": "dry_run" if args.dry_run else "ready",
        "source": SOURCE,
        "duration_sec": 300,
        "image_model": DEFAULT_IMAGE_MODEL,
        "image_attempt_cap": 16,
        "automatic_retries": 0,
        "image_plan": plan,
    }
    _write_json(output_dir / "source-lock.json", {
        **SOURCE,
        "adapted_narration_ru": script["stories"][0]["narration_ru"],
        "adapted_narration_sha256": hashlib.sha256(
            script["stories"][0]["narration_ru"].encode("utf-8"),
        ).hexdigest(),
        "scene_titles": [beat["title"] for beat in BEATS],
    })
    _write_json(output_dir / "image-plan.json", dry_run)
    if args.dry_run:
        return dry_run
    if not args.confirm_spend:
        raise RuntimeError("refusing 16 paid image attempts without --confirm-spend")
    if not load_dotenv_file(args.env_file):
        raise RuntimeError("VectorEngine env file was not found")

    attempts_path = output_dir / "paid-image-attempts.json"
    attempts: list[dict] = []

    def one_attempt(*, prompt: str, output_path: Path, model: str, size: str) -> Path:
        record = {
            "attempt": len(attempts) + 1,
            "model": model,
            "size": size,
            "output": Path(output_path).name,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "status": "started",
        }
        attempts.append(record)
        _write_json(attempts_path, {"cap": 16, "retries": 0, "attempts": attempts})
        try:
            result = call_image_generation(
                prompt=prompt,
                output_path=output_path,
                model=model,
                size=size,
                retries=0,
            )
        except Exception as exc:
            record["status"] = "failed"
            record["error_type"] = type(exc).__name__
            _write_json(attempts_path, {"cap": 16, "retries": 0, "attempts": attempts})
            raise
        record["status"] = "complete"
        record["sha256"] = _sha256(Path(result))
        _write_json(attempts_path, {"cap": 16, "retries": 0, "attempts": attempts})
        return Path(result)

    updated, assets = generate_episode_images(
        script,
        output_dir / "assets",
        max_images=16,
        generator=one_attempt,
        model=DEFAULT_IMAGE_MODEL,
        size="1536x864",
        artifact_root=output_dir,
        visual_mode=EDITORIAL_MOTION_MODE,
        style_profile=style_profile,
    )
    _write_json(output_dir / "episode-with-assets.json", updated)

    intro = "Обычный рабочий день начинается с доверия, а заканчивается чужой версией событий"
    narration = updated["stories"][0]["narration_ru"]
    timings = {
        "intro": _timing(intro, 10.0),
        "story": _timing(narration, 290.0),
    }
    contract = build_editorial_motion_contract(
        narration_segments=[
            {"segment_id": "intro", "kind": "intro", "voice_role": "narrator", "text": intro},
            {"segment_id": "story", "kind": "story", "voice_role": "narrator", "text": narration},
        ],
        segment_timings=timings,
        story_assets={"story": assets},
        story_metadata={
            "intro": {
                "title": "ОДИН ОБЫЧНЫЙ ОФИС",
                "source_label": "REDDIT • ВИЗУАЛЬНЫЙ ПИЛОТ",
                "truth_mode": "source_bound_adaptation",
            },
            "story": {
                "story_index": 1,
                "title": updated["stories"][0]["title_ru"],
                "scene_titles": [beat["title"] for beat in BEATS],
                "source_label": "r/BestofRedditorUpdates • РЕДАКЦИОННАЯ ИЛЛЮСТРАЦИЯ",
                "truth_mode": "source_bound_adaptation",
            },
        },
        final_audio_duration_sec=300.0,
        style_profile=style_profile,
    )
    storyboard = {
        "version": 4,
        "format": "compilation_16x9",
        "resolution": [1920, 1080],
        "fps": 30,
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": style_profile,
        "publication_authorized": False,
        "timeline_duration_sec": 300.0,
        "slides": contract["scenes"],
        "motion_plan": contract["motion_plan"],
        "motion_plan_sha256": contract["motion_plan"]["motion_plan_sha256"],
        "caption_track": contract["caption_track"],
        "caption_track_sha256": contract["caption_track"]["caption_track_sha256"],
    }
    _write_json(output_dir / "storyboard.json", storyboard)
    audio = output_dir / "silent-pilot-audio.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", "300", "-c:a", "pcm_s16le", str(audio),
        ],
        check=True,
        capture_output=True,
    )
    output = output_dir / str(
        getattr(args, "output_filename", "reddit-five-minute-cutup-pilot.mp4"),
    )
    report = render_editorial_motion_compilation(storyboard, output_dir, output, audio=audio)
    contact_sheet = _contact_sheet(output, output_dir)
    report.update({
        "output": output.name,
        "output_sha256": _sha256(output),
        "contact_sheet": contact_sheet.name,
        "source_url": SOURCE["url"],
        "provider_attempts": len(attempts),
        "automatic_retries": 0,
    })
    _write_json(output_dir / "render-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--style-profile", default=EDITORIAL_MOTION_STYLE_PROFILE)
    parser.add_argument("--output-filename", default="reddit-five-minute-cutup-pilot.mp4")
    args = parser.parse_args()
    print(json.dumps(build(args), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
