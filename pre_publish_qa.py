import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_STORY = "story_data.json"
DEFAULT_STORYBOARD = "storyboard.json"
DEFAULT_METADATA = "youtube_metadata.json"
DEFAULT_VIDEO = "final_output.mp4"
DEFAULT_AUDIO = "narration.mp3"
DEFAULT_TRANSCRIPT = "narration.json"
DEFAULT_RENDER_REPORT = "render_report.json"
DEFAULT_OUTPUT = "pre_publish_qa.json"
WORD_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿА-Яа-яЁё]+", re.UNICODE)
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>)\]]+")


class PrePublishQAError(RuntimeError):
    pass


def load_json(path: str | Path, *, required: bool = True) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        if required:
            raise PrePublishQAError(f"Missing required JSON file: {target}")
        return {}
    with target.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise PrePublishQAError(f"{target} must contain a JSON object.")
    return data


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_binary(name: str) -> str | None:
    return shutil.which(name)


def ffprobe_json(path: Path) -> dict[str, Any]:
    ffprobe = find_binary("ffprobe")
    if not ffprobe:
        raise PrePublishQAError("ffprobe is required for pre-publish QA.")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout or "{}")


def stream_count(probe: dict[str, Any], codec_type: str) -> int:
    return sum(
        1
        for stream in probe.get("streams") or []
        if isinstance(stream, dict) and stream.get("codec_type") == codec_type
    )


def media_duration(probe: dict[str, Any]) -> float | None:
    try:
        value = float((probe.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def video_resolution(probe: dict[str, Any]) -> str | None:
    for stream in probe.get("streams") or []:
        if isinstance(stream, dict) and stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            if width and height:
                return f"{width}x{height}"
    return None


def collect_transcript_words(value: Any) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []

    def first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in item and item[key] is not None:
                return item[key]
        return None

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            word = first_present(item, ("word", "text", "token", "value"))
            start = first_present(item, ("start", "startTime", "start_time", "start_ms"))
            end = first_present(item, ("end", "endTime", "end_time", "end_ms"))
            if word and start is not None and end is not None:
                words.append(item)
                return
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return words


def transcript_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "word_count": 0, "timing_status": "missing_file"}
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError, PrePublishQAError):
        return {"exists": True, "word_count": 0, "timing_status": "malformed"}
    return {
        "exists": True,
        "word_count": len(collect_transcript_words(data)),
        "timing_status": str(data.get("timing_status") or "unknown"),
        "voice_mode": data.get("voice_mode"),
    }


def narration_text_parts(story: dict[str, Any]) -> list[str]:
    parts = []
    for field in ("title", "body"):
        value = story.get(f"narration_{field}") or story.get(field)
        if value:
            parts.append(str(value))
    for comment in story.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        value = comment.get("narration_body") or comment.get("body")
        if value:
            parts.append(str(value))
    return parts


def expected_word_count(story: dict[str, Any]) -> int:
    return len(WORD_RE.findall("\n".join(narration_text_parts(story))))


def narration_has_raw_urls(story: dict[str, Any]) -> bool:
    return bool(URL_RE.search("\n".join(narration_text_parts(story))))


def has_hook_evidence(story: dict[str, Any]) -> bool:
    evidence = story.get("hook_evidence")
    if isinstance(evidence, dict):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []
    if any(isinstance(item, dict) and str(item.get("quote") or "").strip() for item in evidence):
        return True
    adaptation = story.get("editorial_adaptation") if isinstance(story.get("editorial_adaptation"), dict) else {}
    adaptation_evidence = adaptation.get("hook_evidence")
    if isinstance(adaptation_evidence, dict):
        adaptation_evidence = [adaptation_evidence]
    if not isinstance(adaptation_evidence, list):
        return False
    return any(isinstance(item, dict) and str(item.get("quote") or "").strip() for item in adaptation_evidence)


def load_channel(channel_id: str | None) -> dict[str, Any] | None:
    if not channel_id:
        return None
    config_path = Path(__file__).with_name("channels.json")
    if not config_path.exists():
        return None
    data = load_json(config_path)
    for channel in data.get("channels") or []:
        if isinstance(channel, dict) and (channel.get("id") == channel_id or channel.get("handle") == channel_id):
            return channel
    return None


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, detail: str, *, required: bool = True) -> None:
    checks.append({
        "name": name,
        "status": "pass" if passed else "fail" if required else "warn",
        "required": required,
        "detail": detail,
    })


def run_qa(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    story = load_json(args.story)
    storyboard = load_json(args.storyboard)
    metadata = load_json(args.metadata)
    render_report = load_json(args.render_report, required=args.require_render_report)
    channel = load_channel(args.channel)

    video_path = Path(args.video)
    audio_path = Path(args.audio)
    transcript_path = Path(args.transcript)

    add_check(checks, "video_exists", video_path.exists() and video_path.stat().st_size > 0, str(video_path))
    video_probe = ffprobe_json(video_path) if video_path.exists() else {}
    video_duration = media_duration(video_probe)
    add_check(checks, "video_stream", stream_count(video_probe, "video") > 0, f"resolution={video_resolution(video_probe)} duration={video_duration}")
    add_check(checks, "video_duration", bool(video_duration and video_duration >= args.min_duration_sec), f"duration={video_duration}")

    has_audio_stream = stream_count(video_probe, "audio") > 0
    add_check(checks, "audio_track_in_video", has_audio_stream, "final MP4 contains audio stream", required=args.require_audio)
    add_check(checks, "narration_mp3_exists", audio_path.exists() and audio_path.stat().st_size > 0, str(audio_path), required=args.require_audio)
    if audio_path.exists():
        audio_probe = ffprobe_json(audio_path)
        audio_duration = media_duration(audio_probe)
        mismatch = abs((video_duration or 0) - (audio_duration or 0)) if video_duration and audio_duration else None
        add_check(
            checks,
            "audio_video_duration_match",
            mismatch is not None and mismatch <= args.max_duration_mismatch_sec,
            f"video={video_duration} audio={audio_duration} mismatch={mismatch}",
            required=args.require_audio,
        )

    expected_words = expected_word_count(story)
    transcript = transcript_status(transcript_path)
    coverage = (transcript["word_count"] / expected_words) if expected_words else 0.0
    add_check(
        checks,
        "karaoke_transcript_words",
        transcript["word_count"] > 0 and coverage >= args.min_karaoke_coverage,
        f"transcript_words={transcript['word_count']} expected_words={expected_words} coverage={coverage:.2f} timing_status={transcript['timing_status']}",
        required=args.require_karaoke,
    )
    if args.require_karaoke:
        add_check(
            checks,
            "render_karaoke_enabled",
            bool(render_report.get("karaokeEnabled")),
            f"karaokeEnabled={render_report.get('karaokeEnabled')} frameSchedule={render_report.get('frameSchedule')}",
            required=True,
        )

    add_check(
        checks,
        "editorial_adaptation",
        isinstance(story.get("editorial_adaptation"), dict),
        "story_data.json has editorial_adaptation",
        required=args.require_adaptation,
    )
    add_check(
        checks,
        "hook_evidence",
        has_hook_evidence(story),
        "source-backed hook evidence is present",
        required=args.require_evidence,
    )
    add_check(
        checks,
        "narration_urls_sanitized",
        not narration_has_raw_urls(story),
        "narration fields do not contain raw URLs",
        required=True,
    )

    title = str(metadata.get("youtube_title") or "")
    add_check(checks, "youtube_title_length", bool(title and len(title) <= 100), f"title_chars={len(title)}")
    if channel:
        expected_lang = channel.get("lang")
        actual_lang = metadata.get("language") or story.get("language")
        add_check(
            checks,
            "language_matches_channel",
            not expected_lang or str(actual_lang or "").lower() == str(expected_lang).lower(),
            f"expected={expected_lang} actual={actual_lang}",
            required=True,
        )
    add_check(
        checks,
        "storyboard_slides",
        bool(storyboard.get("render_slides") or storyboard.get("scenes")),
        f"slides={len(storyboard.get('render_slides') or [])} scenes={len(storyboard.get('scenes') or [])}",
    )

    failures = [check for check in checks if check["status"] == "fail" and check.get("required")]
    warnings = [check for check in checks if check["status"] == "warn"]
    return {
        "version": 1,
        "status": "fail" if failures else "ok",
        "channel": args.channel,
        "video": str(video_path),
        "durationSec": video_duration,
        "resolution": video_resolution(video_probe),
        "expectedNarrationWords": expected_words,
        "transcript": transcript,
        "karaokeCoverage": round(coverage, 4),
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed pre-publish QA for ChonkerTalks videos.")
    parser.add_argument("--story", default=DEFAULT_STORY)
    parser.add_argument("--storyboard", default=DEFAULT_STORYBOARD)
    parser.add_argument("--metadata", default=DEFAULT_METADATA)
    parser.add_argument("--video", default=DEFAULT_VIDEO)
    parser.add_argument("--audio", default=DEFAULT_AUDIO)
    parser.add_argument("--transcript", default=DEFAULT_TRANSCRIPT)
    parser.add_argument("--render-report", default=DEFAULT_RENDER_REPORT)
    parser.add_argument("--channel", "-c")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT)
    parser.add_argument("--require-audio", action="store_true")
    parser.add_argument("--require-karaoke", action="store_true")
    parser.add_argument("--require-adaptation", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    parser.add_argument("--require-render-report", action="store_true")
    parser.add_argument("--min-karaoke-coverage", type=float, default=0.72)
    parser.add_argument("--min-duration-sec", type=float, default=3.0)
    parser.add_argument("--max-duration-mismatch-sec", type=float, default=2.5)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    report = run_qa(args)
    write_json(args.output, report)
    print(json.dumps({
        "status": report["status"],
        "output": args.output,
        "failures": len(report["failures"]),
        "warnings": len(report["warnings"]),
        "karaokeCoverage": report["karaokeCoverage"],
        "durationSec": report["durationSec"],
        "resolution": report["resolution"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError, PrePublishQAError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
