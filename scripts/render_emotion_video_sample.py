#!/usr/bin/env python3
"""Render a short 16:9 emotion/TTS/timed-caption proof from local artifacts."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


class EmotionVideoError(RuntimeError):
    pass


def probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise EmotionVideoError("ffprobe is required")
    result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True)
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise EmotionVideoError("audio duration must be positive")
    return duration


def visible_tokens(text: str) -> list[str]:
    return re.findall(r"\S+", re.sub(r"\[[^\]]+\]", "", str(text or "")))


def estimated_words(text: str, duration: float) -> list[dict[str, Any]]:
    tokens = visible_tokens(text)
    weights = [max(1, len(token.strip())) for token in tokens]
    total = max(1, sum(weights))
    cursor = 0.0
    words = []
    for index, (token, weight) in enumerate(zip(tokens, weights)):
        end = duration if index == len(tokens) - 1 else cursor + duration * weight / total
        words.append({"word": token, "start": round(cursor, 3), "end": round(end, 3), "timing_source": "estimated"})
        cursor = end
    return words


def caption_chunks(words: list[dict[str, Any]], *, max_words: int = 10, max_chars: int = 72) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        token = str(word.get("word") or "").strip()
        if not token:
            continue
        candidate = " ".join([str(item["word"]) for item in current] + [token])
        if current and (len(current) >= max_words or len(candidate) > max_chars):
            chunks.append({"start": float(current[0]["start"]), "end": float(current[-1]["end"]),
                           "text": " ".join(str(item["word"]) for item in current)})
            current = []
        current.append({**word, "word": token})
        if len(current) >= 4 and re.search(r"[,;:—.!?…][\"»)]?$", token):
            chunks.append({"start": float(current[0]["start"]), "end": float(current[-1]["end"]),
                           "text": " ".join(str(item["word"]) for item in current)})
            current = []
    if current:
        chunks.append({"start": float(current[0]["start"]), "end": float(current[-1]["end"]),
                       "text": " ".join(str(item["word"]) for item in current)})
    for index in range(len(chunks) - 1):
        chunks[index]["end"] = max(chunks[index]["end"], chunks[index + 1]["start"])
    return chunks


def ass_time(seconds: float) -> str:
    value = max(0.0, float(seconds))
    hours = int(value // 3600)
    minutes = int(value % 3600 // 60)
    secs = value % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def ass_escape(text: str) -> str:
    return str(text).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def write_ass(chunks: list[dict[str, Any]], path: Path) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,52,&H00FFFFFF,&H000000FF,&H00101010,&H78000000,-1,0,0,0,100,100,0,0,3,3,0,2,150,150,105,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [f"Dialogue: 0,{ass_time(item['start'])},{ass_time(item['end'])},Caption,,0,0,0,,{ass_escape(item['text'])}"
              for item in chunks]
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def write_reddit_pages_ass(
    chunks: list[dict[str, Any]], path: Path, *, duration: float,
    title: str = "Ночная смена: последнее правило",
    chunks_per_page: int = 3,
) -> None:
    if chunks_per_page < 1:
        raise EmotionVideoError("chunks_per_page must be positive")
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Meta,DejaVu Sans,28,&H00E4E7EB,&H000000FF,&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,2,2,7,150,150,90,1
Style: Title,DejaVu Sans,52,&H00FFFFFF,&H000000FF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,7,150,150,90,1
Style: Body,DejaVu Sans,43,&H00FFFFFF,&H000000FF,&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,3,2,7,150,150,90,1
Style: Actions,DejaVu Sans,30,&H00E4E7EB,&H000000FF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,2,2,8,150,150,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    page_count = (len(chunks) + chunks_per_page - 1) // chunks_per_page
    for page_index in range(page_count):
        page = chunks[page_index * chunks_per_page:(page_index + 1) * chunks_per_page]
        page_start = float(page[0]["start"])
        page_end = float(chunks[(page_index + 1) * chunks_per_page]["start"]) if page_index + 1 < page_count else duration
        if page_index == 0:
            events.append(f"Dialogue: 0,{ass_time(page_start)},{ass_time(page_end)},Meta,,0,0,0,,{{\\pos(150,80)\\fad(150,180)}}r/NoSleep  •  опубликовано пользователем u/anonymous")
            events.append(f"Dialogue: 0,{ass_time(page_start)},{ass_time(page_end)},Title,,0,0,0,,{{\\pos(150,135)\\fad(150,180)}}{ass_escape(title)}")
            base_y = 255
        else:
            base_y = 125
        for row, item in enumerate(page):
            start = float(item["start"])
            y = base_y + row * 185
            text = ass_escape(str(item["text"]))
            events.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(page_end)},Body,,0,0,0,,"
                f"{{\\pos(150,{y})\\fad(120,180)}}{text}"
            )
    actions_start = max(0.0, duration - 3.2)
    events.append(
        f"Dialogue: 1,{ass_time(actions_start)},{ass_time(duration)},Actions,,0,0,0,,"
        "{\\fad(180,120)}▲ 12,4 тыс.     Комментарии 438     Поделиться     Сохранить"
    )
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def render(background: Path, audio: Path, captions: Path, output: Path, duration: float, *, direct_background: bool = False) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise EmotionVideoError("ffmpeg is required")
    frames = max(1, round(duration * 30))
    escaped_ass = str(captions.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    grade = "eq=brightness=-0.01:saturation=0.92" if direct_background else "eq=brightness=-0.04:saturation=0.90,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.08:t=fill"
    vf = (
        f"scale=2200:1238:force_original_aspect_ratio=increase,crop=2200:1238,"
        f"zoompan=z='min(zoom+0.00012,1.08)':x='iw/2-(iw/zoom/2)+sin(on/180)*12':"
        f"y='ih/2-(ih/zoom/2)+cos(on/220)*8':d={frames}:s=1920x1080:fps=30,"
        f"{grade},"
        f"ass='{escaped_ass}'"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(background), "-i", str(audio),
        "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-t", f"{duration:.3f}", "-r", "30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--background", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--style", choices=("captions", "reddit_pages"), default="captions")
    parser.add_argument("--reddit-title", default="Ночная смена: последнее правило")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    samples = [sample for channel in manifest.get("channels") or [] for sample in channel.get("samples") or []
               if sample.get("role") == "narrator"]
    if len(samples) != 1:
        raise EmotionVideoError("manifest must contain exactly one narrator sample")
    sample = samples[0]
    manifest_dir = Path(args.manifest).resolve().parent
    audio = Path(sample["file"])
    if not audio.is_file():
        audio = manifest_dir / audio.name
    duration = probe_duration(audio)
    timing_path = Path(str(sample.get("timings_file") or ""))
    if not timing_path.is_file():
        timing_path = manifest_dir / timing_path.name
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.is_file() else {}
    words = timing.get("words") if isinstance(timing.get("words"), list) else []
    timing_source = "ai33" if words else "estimated"
    if not words:
        words = estimated_words(str(sample.get("text") or ""), duration)
    chunks = caption_chunks(words)
    if not chunks:
        raise EmotionVideoError("no caption chunks available")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ass_path = output_dir / "captions.ass"
    if args.style == "reddit_pages":
        write_reddit_pages_ass(chunks, ass_path, duration=duration, title=args.reddit_title)
    else:
        write_ass(chunks, ass_path)
    video_path = output_dir / "emotion-video-sample.mp4"
    render(Path(args.background), audio, ass_path, video_path, duration,
           direct_background=args.style == "reddit_pages")
    (output_dir / "emotion-video-report.json").write_text(json.dumps({
        "status": "PASS", "duration": round(duration, 3), "caption_chunks": len(chunks),
        "timing_source": timing_source, "style": args.style,
        "video": str(video_path), "audio": str(audio),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
