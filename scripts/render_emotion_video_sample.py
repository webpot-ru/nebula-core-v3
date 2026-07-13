#!/usr/bin/env python3
"""Render a short 16:9 emotion/TTS/timed-caption proof from local artifacts."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import textwrap
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


def fixed_wrapped_prefix(full_text: str, prefix_text: str, *, line_chars: int = 76) -> str:
    """Reveal a prefix inside the final page wrapping so earlier lines never reflow."""
    if line_chars < 20:
        raise EmotionVideoError("Reddit line width is too small")
    full_words = str(full_text or "").split()
    prefix_words = str(prefix_text or "").split()
    if prefix_words != full_words[:len(prefix_words)]:
        raise EmotionVideoError("Reddit reveal text must be a prefix of the final page")
    final_lines = textwrap.wrap(
        " ".join(full_words), width=line_chars, break_long_words=False,
        break_on_hyphens=False, replace_whitespace=True, drop_whitespace=True,
    )
    remaining = len(prefix_words)
    revealed: list[str] = []
    cursor = 0
    for line in final_lines:
        line_word_count = len(line.split())
        take = min(remaining, line_word_count)
        if take <= 0:
            break
        revealed.append(" ".join(full_words[cursor:cursor + take]))
        cursor += line_word_count
        remaining -= take
    return r"\N".join(revealed)


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
    first_page_chars: int = 700,
    continuation_page_chars: int = 900,
    line_chars: int = 76,
) -> None:
    if first_page_chars < 40 or continuation_page_chars < 40:
        raise EmotionVideoError("Reddit page character capacities are too small")
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Meta,Reddit Sans,28,&H00A9B8BA,&H000000FF,&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,80,80,70,1
Style: Title,Reddit Sans,46,&H00F2F4F5,&H000000FF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,1,0,7,80,80,70,1
Style: Body,Reddit Sans,40,&H00CFD7D8,&H000000FF,&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,80,80,70,1
Style: ActionText,Reddit Sans,27,&H00A9B8BA,&H000000FF,&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1
Style: ActionIcon,Reddit Sans,24,&H00A9B8BA,&H000000FF,&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1
Style: OutlineIcon,Reddit Sans,24,&HFFA9B8BA,&H000000FF,&H00A9B8BA,&H00000000,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in chunks:
        capacity = first_page_chars if not pages else continuation_page_chars
        candidate = " ".join([str(value["text"]) for value in current] + [str(item["text"])])
        if current and len(candidate) > capacity:
            pages.append(current)
            current = []
        current.append(item)
    if current:
        pages.append(current)

    for page_index, page in enumerate(pages):
        page_start = float(page[0]["start"])
        page_end = float(pages[page_index + 1][0]["start"]) if page_index + 1 < len(pages) else duration
        if page_index == 0:
            events.append(f"Dialogue: 0,{ass_time(page_start)},{ass_time(page_end)},ActionIcon,,0,0,0,,{{\\pos(80,78)\\c&H000045FF\\p1}}m 23 0 b 36 0 46 10 46 23 b 46 36 36 46 23 46 b 10 46 0 36 0 23 b 0 10 10 0 23 0{{\\p0}}")
            events.append(f"Dialogue: 1,{ass_time(page_start)},{ass_time(page_end)},Meta,,0,0,0,,{{\\pos(142,83)}}{{\\b1}}u/anonymous{{\\b0}}  •  10 ч. назад")
            events.append(f"Dialogue: 0,{ass_time(page_start)},{ass_time(page_end)},Title,,0,0,0,,{{\\pos(80,155)}}{ass_escape(title)}")
            base_y = 245
        else:
            base_y = 90
        full_page_text = " ".join(str(value["text"]) for value in page)
        accumulated: list[str] = []
        for row, item in enumerate(page):
            start = float(item["start"])
            end = float(page[row + 1]["start"]) if row + 1 < len(page) else page_end
            accumulated.append(str(item["text"]))
            text = fixed_wrapped_prefix(full_page_text, " ".join(accumulated), line_chars=line_chars)
            escaped_text = ass_escape(text).replace(r"\\N", r"\N")
            events.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Body,,0,0,0,,"
                f"{{\\pos(80,{base_y})}}{escaped_text}"
            )
    actions_start = max(float(chunks[0]["start"]), duration - 3.2)
    action_window = f"{ass_time(actions_start)},{ass_time(duration)}"
    vector_actions = [
        (86, "m 14 0 l 28 16 l 20 16 l 20 34 l 8 34 l 8 16 l 0 16"),
        (245, "m 0 18 l 14 34 l 28 18 l 20 18 l 20 0 l 8 0 l 8 18"),
        (330, "m 1 2 l 31 2 l 31 24 l 13 24 l 5 32 l 5 24 l 1 24"),
        (575, "m 0 30 b 8 12 18 8 28 8 l 28 0 l 42 14 l 28 28 l 28 20 b 16 18 8 22 0 30"),
    ]
    for x, drawing in vector_actions:
        events.append(f"Dialogue: 3,{action_window},OutlineIcon,,0,0,0,,{{\\pos({x},972)\\p1}}{drawing}{{\\p0}}")
    action_labels = [(137, "12,4 тыс."), (378, "Ответить"), (623, "Поделиться"), (840, "•••")]
    for x, label in action_labels:
        events.append(f"Dialogue: 3,{action_window},ActionText,,0,0,0,,{{\\pos({x},975)}}{ass_escape(label)}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def render(
    background: Path, audio: Path, captions: Path, output: Path, duration: float,
    *, direct_background: bool = False, font_dir: Path | None = None,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise EmotionVideoError("ffmpeg is required")
    background_is_video = background.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
    frames = max(1, round(duration * 30))
    escaped_ass = str(captions.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    grade = "eq=brightness=-0.01:saturation=0.92" if direct_background else "eq=brightness=-0.04:saturation=0.90,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.08:t=fill"
    ass_filter = f"ass='{escaped_ass}'"
    if font_dir is not None:
        if not font_dir.is_dir():
            raise EmotionVideoError(f"font directory does not exist: {font_dir}")
        escaped_fonts = str(font_dir.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        ass_filter += f":fontsdir='{escaped_fonts}'"
    if background_is_video:
        vf = (
            "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,"
            f"{grade}," + ass_filter
        )
        background_args = ["-stream_loop", "-1", "-i", str(background)]
    else:
        vf = (
            f"scale=2200:1238:force_original_aspect_ratio=increase,crop=2200:1238,"
            f"zoompan=z='min(zoom+0.00012,1.08)':x='iw/2-(iw/zoom/2)+sin(on/180)*12':"
            f"y='ih/2-(ih/zoom/2)+cos(on/220)*8':d={frames}:s=1920x1080:fps=30,"
            f"{grade}," + ass_filter
        )
        background_args = ["-loop", "1", "-i", str(background)]
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-v", "error", *background_args, "-i", str(audio),
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
    parser.add_argument("--reddit-line-chars", type=int, default=76)
    parser.add_argument("--font-dir", help="Directory containing Reddit Sans for ASS rendering")
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
        write_reddit_pages_ass(chunks, ass_path, duration=duration, title=args.reddit_title,
                               line_chars=args.reddit_line_chars)
    else:
        write_ass(chunks, ass_path)
    video_path = output_dir / "emotion-video-sample.mp4"
    font_dir = Path(args.font_dir) if args.font_dir else None
    if args.style == "reddit_pages" and font_dir is None:
        raise EmotionVideoError("reddit_pages requires --font-dir with the official Reddit Sans font")
    render(Path(args.background), audio, ass_path, video_path, duration,
           direct_background=args.style == "reddit_pages", font_dir=font_dir)
    (output_dir / "emotion-video-report.json").write_text(json.dumps({
        "status": "PASS", "duration": round(duration, 3), "caption_chunks": len(chunks),
        "timing_source": timing_source, "style": args.style,
        "video": str(video_path), "audio": str(audio),
        "reddit_layout": ({
            "font_family": "Reddit Sans",
            "font_sizes_px": {"meta": 28, "title": 46, "body": 40, "actions": 27},
            "left_right_margin_px": 80,
            "header_avatar_px": 46,
            "positions_y_px": {"header": 83, "title": 155, "body": 245, "actions": 975},
            "line_measure_chars": args.reddit_line_chars,
            "page_capacity_chars": {"first": 700, "continuation": 900},
            "actions_visible_final_seconds": 3.2,
        } if args.style == "reddit_pages" else None),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
