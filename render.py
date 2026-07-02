import argparse
import base64
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_STORYBOARD = "storyboard.json"
DEFAULT_OUTPUT = "final_output.mp4"
DEFAULT_WORKDIR = "build/render"
DEFAULT_FRAME_COUNT = 8
DEFAULT_OUTPUT_FPS = 30
DEFAULT_BROWSER_TIMEOUT_SECONDS = 45
DEFAULT_AUDIO = "narration.mp3"
DEFAULT_TRANSCRIPT = "narration.json"
LONG_FORM_THRESHOLD_SECONDS = 180.0
VERTICAL_PROFILE = {
    "format": "shorts",
    "width": 1080,
    "height": 1920,
    "aspect": "ratio-9-16",
    "layout": "layout-mobile",
}
HORIZONTAL_PROFILE = {
    "format": "long",
    "width": 1920,
    "height": 1080,
    "aspect": "ratio-16-9",
    "layout": "layout-desktop",
}

BROWSER_CANDIDATES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


class RenderError(RuntimeError):
    pass


class CDPClient:
    def __init__(self, websocket_url: str) -> None:
        parsed = urllib.parse.urlparse(websocket_url)
        if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
            raise RenderError(f"Unsupported DevTools websocket URL: {websocket_url}")
        self.sock = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
        self.sock.settimeout(10)
        self.next_id = 0

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RenderError("Chrome DevTools websocket handshake failed.")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def command(self, method: str, params: dict[str, Any] | None = None, timeout: float = 10) -> dict[str, Any]:
        self.next_id += 1
        message_id = self.next_id
        payload = {"id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send_text(json.dumps(payload, separators=(",", ":")))

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self._receive_json(deadline - time.monotonic())
            except (OSError, TimeoutError) as exc:
                raise RenderError(f"Timed out or lost connection waiting for CDP {method}: {exc}") from exc
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise RenderError(f"CDP {method} failed: {message['error']}")
            result = message.get("result")
            return result if isinstance(result, dict) else {}
        raise RenderError(f"Timed out waiting for CDP {method}.")

    def _send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        self._send_frame(0x1, payload)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))

        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _receive_json(self, timeout: float) -> dict[str, Any]:
        self.sock.settimeout(max(timeout, 0.1))
        while True:
            opcode, payload = self._read_frame()
            if opcode == 0x1:
                return json.loads(payload.decode("utf-8"))
            if opcode == 0x8:
                raise RenderError("Chrome DevTools websocket closed.")
            if opcode == 0x9:
                self._send_frame(0xA, payload)

    def _read_frame(self) -> tuple[int, bytes]:
        header = self._read_exact(2)
        first, second = header[0], header[1]
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(self._read_exact(2), "big")
        elif length == 127:
            length = int.from_bytes(self._read_exact(8), "big")

        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload

    def _read_exact(self, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.sock.recv(length - len(chunks))
            if not chunk:
                raise RenderError("Chrome DevTools websocket closed unexpectedly.")
            chunks.extend(chunk)
        return bytes(chunks)


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RenderError(f"{path} must contain a JSON object.")
    return data


def find_ffmpeg_binary(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise RenderError(f"Missing `{name}`. Install FFmpeg before rendering.")
    return binary


def probe_media_duration(ffprobe: str, media_path: Path) -> float | None:
    if not media_path.exists():
        return None
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


def find_browser_binary() -> str:
    for candidate in BROWSER_CANDIDATES:
        if "/" in candidate:
            if Path(candidate).exists():
                return candidate
        else:
            binary = shutil.which(candidate)
            if binary:
                return binary
    raise RenderError("Missing Chrome/Chromium. Install Google Chrome or Chromium for RedditSim rendering.")


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_http_json(url: str, timeout: float = 1.0, method: str = "GET") -> Any:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def start_cdp_browser(browser: str, workdir: Path, width: int, height: int) -> tuple[subprocess.Popen[bytes], CDPClient]:
    port = find_free_port()
    chrome_profile = workdir / f"chrome-cdp-profile-{time.time_ns()}"
    chrome_profile.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen([
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--allow-file-access-from-files",
        "--disable-web-security",
        "--disable-dev-shm-usage",
        "--disable-features=OptimizationHints,AutofillServerCommunication,MediaRouter",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={chrome_profile}",
        f"--window-size={width},{height}",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    version_url = f"http://127.0.0.1:{port}/json/version"
    deadline = time.monotonic() + DEFAULT_BROWSER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RenderError(f"Chrome exited before DevTools became available: {process.returncode}")
        try:
            read_http_json(version_url)
            break
        except (OSError, json.JSONDecodeError, http.client.HTTPException):
            time.sleep(0.2)
    else:
        stop_browser(process)
        raise RenderError("Chrome DevTools endpoint did not become available.")

    targets = read_http_json(f"http://127.0.0.1:{port}/json/list")
    if not isinstance(targets, list):
        stop_browser(process)
        raise RenderError("Chrome DevTools target list was not a JSON array.")
    target = next(
        (
            item for item in targets
            if isinstance(item, dict) and item.get("type") == "page" and isinstance(item.get("webSocketDebuggerUrl"), str)
        ),
        None,
    )
    if not isinstance(target, dict):
        stop_browser(process)
        raise RenderError("Chrome DevTools did not expose a page target.")
    websocket_url = target.get("webSocketDebuggerUrl")
    if not isinstance(websocket_url, str):
        stop_browser(process)
        raise RenderError("Chrome did not return a page DevTools websocket URL.")

    client = CDPClient(websocket_url)
    client.command("Page.enable")
    client.command("Runtime.enable")
    client.command("Emulation.setDeviceMetricsOverride", {
        "width": width,
        "height": height,
        "deviceScaleFactor": 1,
        "mobile": False,
    })
    return process, client


def stop_browser(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def wait_for_render_ready(client: CDPClient) -> None:
    expression = """
(() => {
  if (document.body && document.body.dataset.renderError) return `error:${document.body.dataset.renderError}`;
  if (document.body && ['true', 'karaoke', 'done'].includes(document.body.dataset.renderReady)) return 'ready';
  return document.readyState || 'loading';
})()
"""
    deadline = time.monotonic() + DEFAULT_BROWSER_TIMEOUT_SECONDS
    last_value = ""
    while time.monotonic() < deadline:
        try:
            result = client.command("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True,
            }, timeout=2)
            value = result.get("result", {}).get("value", "")
        except RenderError:
            time.sleep(0.2)
            continue
        last_value = str(value)
        if last_value == "ready":
            return
        if last_value.startswith("error:"):
            raise RenderError(last_value)
        time.sleep(0.2)
    raise RenderError(f"Timed out waiting for RedditSim render mode. Last state: {last_value}")


def storyboard_duration(storyboard: dict[str, Any]) -> float:
    scenes = storyboard.get("scenes") or []
    duration = sum(float(scene.get("duration_sec") or 0) for scene in scenes if isinstance(scene, dict))
    return max(duration, 3.0)


def resolve_render_profile(
    storyboard: dict[str, Any],
    duration: float,
    orientation: str,
    long_form_threshold_sec: float,
) -> dict[str, Any]:
    if orientation == "horizontal":
        return dict(HORIZONTAL_PROFILE)
    if orientation == "vertical":
        return dict(VERTICAL_PROFILE)
    if duration > long_form_threshold_sec:
        return dict(HORIZONTAL_PROFILE)

    resolution = storyboard.get("resolution") or {}
    try:
        width = int(resolution.get("width") or VERTICAL_PROFILE["width"])
        height = int(resolution.get("height") or VERTICAL_PROFILE["height"])
    except (TypeError, ValueError):
        width = int(VERTICAL_PROFILE["width"])
        height = int(VERTICAL_PROFILE["height"])

    if width > height:
        profile = dict(HORIZONTAL_PROFILE)
    else:
        profile = dict(VERTICAL_PROFILE)
    profile["width"] = width
    profile["height"] = height
    return profile


def resolve_optional_file(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def coerce_transcript_seconds(value: Any, key: str = "") -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if "ms" in key.lower() or parsed > 1000:
        return parsed / 1000
    return parsed


def normalize_transcript_word(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    word = first_present(value, ("word", "text", "punctuated_word", "token", "value"))
    if not word:
        return None

    start_key = ""
    start_raw = None
    for key in ("start", "startTime", "start_time", "startMs", "start_ms", "begin", "beginTime", "begin_time", "beginMs", "begin_ms", "offset", "offsetMs", "offset_ms"):
        if key in value and value[key] is not None:
            start_key = key
            start_raw = value[key]
            break
    end_key = ""
    end_raw = None
    for key in ("end", "endTime", "end_time", "endMs", "end_ms", "finish", "finishTime", "finish_time", "stop", "stopTime", "stop_time"):
        if key in value and value[key] is not None:
            end_key = key
            end_raw = value[key]
            break

    start = coerce_transcript_seconds(start_raw, start_key)
    end = coerce_transcript_seconds(end_raw, end_key)
    if end is None and start is not None:
        for key in ("duration", "durationTime", "duration_time", "durationMs", "duration_ms"):
            if key in value and value[key] is not None:
                duration = coerce_transcript_seconds(value[key], key)
                if duration is not None:
                    end = start + duration
                    break
    if start is None or end is None or end < start:
        return None
    return {"word": str(word), "start": start, "end": end}


def count_transcript_words(value: Any) -> int:
    if normalize_transcript_word(value):
        return 1
    if isinstance(value, dict):
        return sum(count_transcript_words(item) for item in value.values())
    if isinstance(value, list):
        return sum(count_transcript_words(item) for item in value)
    return 0


def transcript_word_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(data, dict) and str(data.get("timing_status") or "").lower() in {"missing", "partial"}:
        return 0
    return count_transcript_words(data)


def write_render_story(storyboard: dict[str, Any], workdir: Path) -> Path:
    render_story = storyboard.get("render_story")
    if not isinstance(render_story, dict):
        raise RenderError(
            "storyboard.json has no render_story object. Regenerate it with storyboard_generator.py."
        )
    render_payload = dict(render_story)
    render_slides = storyboard.get("render_slides")
    if isinstance(render_slides, list) and render_slides and not isinstance(render_payload.get("slides"), list):
        render_payload["slides"] = render_slides
    story_path = workdir / "render_story.json"
    story_path.write_text(json.dumps(render_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return story_path


def capture_redditsim_frames(
    *,
    browser: str,
    story_path: Path,
    audio_path: Path | None,
    transcript_path: Path | None,
    workdir: Path,
    duration: float,
    frame_count: int,
    width: int,
    height: int,
    aspect_ratio: str,
    layout_style: str,
) -> list[Path]:
    frames_dir = workdir / f"frames_{time.time_ns()}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_count = max(2, frame_count)
    index_url = (PROJECT_ROOT / "index.html").resolve().as_uri()
    story_url = story_path.resolve().as_uri()
    query_parts = [
        ("render", "1"),
        ("capture", "1"),
        ("story", story_url),
        ("aspect", aspect_ratio),
        ("layout", layout_style),
    ]
    if audio_path:
        query_parts.append(("audio", audio_path.resolve().as_uri()))
    if transcript_path:
        query_parts.append(("transcript", transcript_path.resolve().as_uri()))
        query_parts.append(("karaoke", "1"))
    encoded_query = urllib.parse.urlencode(query_parts, quote_via=urllib.parse.quote, safe=":/")
    frames: list[Path] = []

    process, client = start_cdp_browser(browser, frames_dir, width, height)
    try:
        # Load index page once
        initial_url = f"{index_url}?{encoded_query}"
        client.command("Page.navigate", {"url": initial_url}, timeout=5)
        wait_for_render_ready(client)

        for frame_index in range(frame_count):
            progress = frame_index / (frame_count - 1)
            screenshot_path = frames_dir / f"frame_{frame_index:04d}.png"

            # Update typing/karaoke progress in-memory via JavaScript.
            timestamp = progress * duration
            if transcript_path:
                expression = (
                    "(() => { "
                    "if (!window.karaokeReady) { throw new Error('Karaoke transcript is required but not ready.'); } "
                    f"return renderKaraokeAtTime({timestamp:.6f}); "
                    "})()"
                )
            else:
                expression = f"renderTypingAtProgress({progress:.6f})"
            evaluation = client.command("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True,
            }, timeout=5)
            if evaluation.get("exceptionDetails"):
                details = evaluation["exceptionDetails"]
                description = details.get("exception", {}).get("description") or details.get("text") or "unknown JavaScript error"
                raise RenderError(f"RedditSim frame update failed: {description}")

            screenshot = client.command("Page.captureScreenshot", {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": False,
            }, timeout=10)
            image_data = screenshot.get("data")
            if not isinstance(image_data, str):
                raise RenderError(f"Chrome did not return screenshot data for frame {frame_index + 1}/{frame_count}.")
            screenshot_path.write_bytes(base64.b64decode(image_data))
            frames.append(screenshot_path)
    finally:
        client.close()
        stop_browser(process)
    return frames


def encode_frames(
    ffmpeg: str,
    frames_dir: Path,
    output_path: Path,
    duration: float,
    frame_count: int,
    audio_path: Path | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    input_framerate = max(frame_count / max(duration, 0.1), 0.1)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        f"{input_framerate:.6f}",
        "-i",
        str(frames_dir / "frame_%04d.png"),
    ]
    if audio_path:
        command.extend(["-i", str(audio_path)])
    command.extend([
        "-vf",
        f"fps={DEFAULT_OUTPUT_FPS},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
    ])
    if audio_path:
        command.extend([
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-af",
            "aresample=async=1:first_pts=0",
        ])
    command.extend([
        "-t",
        f"{duration:.3f}",
        "-movflags",
        "+faststart",
        str(output_path),
    ])
    run_command(command)


def render_redditsim_video(
    *,
    storyboard: dict[str, Any],
    output_path: Path,
    workdir: Path,
    frame_count: int,
    orientation: str,
    long_form_threshold_sec: float,
    audio_path: Path | None,
    transcript_path: Path | None,
    transcript_word_count_value: int,
) -> dict[str, Any]:
    ffmpeg = find_ffmpeg_binary("ffmpeg")
    ffprobe = find_ffmpeg_binary("ffprobe")
    browser = find_browser_binary()
    story_path = write_render_story(storyboard, workdir)
    storyboard_sec = storyboard_duration(storyboard)
    audio_sec = probe_media_duration(ffprobe, audio_path) if audio_path else None
    duration = audio_sec or storyboard_sec
    render_profile = resolve_render_profile(storyboard, duration, orientation, long_form_threshold_sec)
    width = int(render_profile["width"])
    height = int(render_profile["height"])
    frames = capture_redditsim_frames(
        browser=browser,
        story_path=story_path,
        audio_path=audio_path,
        transcript_path=transcript_path,
        workdir=workdir,
        duration=duration,
        frame_count=frame_count,
        width=width,
        height=height,
        aspect_ratio=str(render_profile["aspect"]),
        layout_style=str(render_profile["layout"]),
    )
    encode_frames(ffmpeg, frames[0].parent, output_path, duration, len(frames), audio_path)

    return {
        "browser": browser,
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "framesDir": str(frames[0].parent),
        "frameCount": len(frames),
        "durationSec": duration,
        "storyboardDurationSec": storyboard_sec,
        "audioDurationSec": audio_sec,
        "audio": str(audio_path) if audio_path else None,
        "transcript": str(transcript_path) if transcript_path else None,
        "transcriptWordCount": transcript_word_count_value,
        "karaokeEnabled": bool(transcript_path),
        "outputFps": DEFAULT_OUTPUT_FPS,
        "renderFormat": render_profile["format"],
        "resolution": f"{width}x{height}",
        "aspectRatio": render_profile["aspect"],
        "layoutStyle": render_profile["layout"],
        "longFormThresholdSec": long_form_threshold_sec,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a dry-run MP4 from storyboard.json using the RedditSim UI.")
    parser.add_argument("--storyboard", default=DEFAULT_STORYBOARD, help="Input storyboard JSON path.")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output MP4 path.")
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR, help="Renderer working directory.")
    parser.add_argument("--frame-count", type=int, default=DEFAULT_FRAME_COUNT, help="Number of RedditSim screenshots to sample across the storyboard.")
    parser.add_argument("--audio", default=DEFAULT_AUDIO, help="Optional narration audio path to merge into the MP4.")
    parser.add_argument("--transcript", default=DEFAULT_TRANSCRIPT, help="Optional word-level transcript JSON path for karaoke highlighting.")
    parser.add_argument(
        "--orientation",
        choices=["auto", "vertical", "horizontal"],
        default="auto",
        help="Render orientation. In auto mode, videos longer than --long-form-threshold-sec render as horizontal 16:9.",
    )
    parser.add_argument(
        "--long-form-threshold-sec",
        type=float,
        default=LONG_FORM_THRESHOLD_SECONDS,
        help="Duration threshold above which --orientation auto renders horizontal 16:9 video.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    storyboard = load_json(args.storyboard)
    scenes = storyboard.get("scenes") or []
    if not scenes:
        raise RenderError(f"{args.storyboard} has no scenes.")

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    audio_path = resolve_optional_file(args.audio)
    transcript_path = resolve_optional_file(args.transcript)
    transcript_words = transcript_word_count(transcript_path) if transcript_path else 0
    if transcript_path and transcript_words <= 0:
        print(
            f"WARNING: {transcript_path} has no usable word timings; "
            "rendering clean slide-progress frames and keeping narration audio.",
            file=sys.stderr,
        )
        transcript_path = None
    if transcript_path and not audio_path:
        raise RenderError("--transcript was found, but --audio is missing; karaoke render needs both.")

    output_path = Path(args.output)
    render_result = render_redditsim_video(
        storyboard=storyboard,
        output_path=output_path,
        workdir=workdir,
        frame_count=args.frame_count,
        orientation=args.orientation,
        long_form_threshold_sec=args.long_form_threshold_sec,
        audio_path=audio_path,
        transcript_path=transcript_path,
        transcript_word_count_value=transcript_words if transcript_path else 0,
    )
    print(json.dumps({
        "status": "ok",
        "storyboard": args.storyboard,
        "output": str(output_path),
        "sceneCount": len(scenes),
        "captureFrameCount": args.frame_count,
        **render_result,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError, RenderError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
