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
DEFAULT_BROWSER_TIMEOUT_SECONDS = 20

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
  if (document.body && document.body.dataset.renderReady === 'true') return 'ready';
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


def write_render_story(storyboard: dict[str, Any], workdir: Path) -> Path:
    render_story = storyboard.get("render_story")
    if not isinstance(render_story, dict):
        raise RenderError(
            "storyboard.json has no render_story object. Regenerate it with storyboard_generator.py."
        )
    story_path = workdir / "render_story.json"
    story_path.write_text(json.dumps(render_story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return story_path


def capture_redditsim_frames(
    *,
    browser: str,
    story_path: Path,
    workdir: Path,
    duration: float,
    frame_count: int,
    width: int,
    height: int,
) -> list[Path]:
    frames_dir = workdir / f"frames_{time.time_ns()}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_count = max(2, frame_count)
    index_url = (PROJECT_ROOT / "index.html").resolve().as_uri()
    story_url = story_path.resolve().as_uri()
    encoded_story_url = urllib.parse.quote(story_url, safe=":/")
    frames: list[Path] = []

    process, client = start_cdp_browser(browser, frames_dir, width, height)
    try:
        # Load index page once
        initial_url = f"{index_url}?render=1&story={encoded_story_url}"
        client.command("Page.navigate", {"url": initial_url}, timeout=5)
        wait_for_render_ready(client)

        for frame_index in range(frame_count):
            progress = frame_index / (frame_count - 1)
            screenshot_path = frames_dir / f"frame_{frame_index:04d}.png"
            
            # Update typing animation progress in-memory via JavaScript
            client.command("Runtime.evaluate", {
                "expression": f"renderTypingAtProgress({progress:.6f})",
                "returnByValue": True,
            }, timeout=5)

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


def encode_frames(ffmpeg: str, frames_dir: Path, output_path: Path, duration: float, frame_count: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    input_framerate = max(frame_count / max(duration, 0.1), 0.1)
    run_command([
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        f"{input_framerate:.6f}",
        "-i",
        str(frames_dir / "frame_%04d.png"),
        "-t",
        f"{duration:.3f}",
        "-vf",
        f"fps={DEFAULT_OUTPUT_FPS},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-movflags",
        "+faststart",
        str(output_path),
    ])


def render_redditsim_video(
    *,
    storyboard: dict[str, Any],
    output_path: Path,
    workdir: Path,
    frame_count: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    ffmpeg = find_ffmpeg_binary("ffmpeg")
    browser = find_browser_binary()
    story_path = write_render_story(storyboard, workdir)
    duration = storyboard_duration(storyboard)
    frames = capture_redditsim_frames(
        browser=browser,
        story_path=story_path,
        workdir=workdir,
        duration=duration,
        frame_count=frame_count,
        width=width,
        height=height,
    )
    encode_frames(ffmpeg, frames[0].parent, output_path, duration, len(frames))

    return {
        "browser": browser,
        "ffmpeg": ffmpeg,
        "framesDir": str(frames[0].parent),
        "frameCount": len(frames),
        "durationSec": duration,
        "outputFps": DEFAULT_OUTPUT_FPS,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a dry-run MP4 from storyboard.json using the RedditSim UI.")
    parser.add_argument("--storyboard", default=DEFAULT_STORYBOARD, help="Input storyboard JSON path.")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output MP4 path.")
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR, help="Renderer working directory.")
    parser.add_argument("--frame-count", type=int, default=DEFAULT_FRAME_COUNT, help="Number of RedditSim screenshots to sample across the storyboard.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    storyboard = load_json(args.storyboard)
    scenes = storyboard.get("scenes") or []
    if not scenes:
        raise RenderError(f"{args.storyboard} has no scenes.")

    resolution = storyboard.get("resolution") or {}
    width = int(resolution.get("width") or 1080)
    height = int(resolution.get("height") or 1920)
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    output_path = Path(args.output)
    render_result = render_redditsim_video(
        storyboard=storyboard,
        output_path=output_path,
        workdir=workdir,
        frame_count=args.frame_count,
        width=width,
        height=height,
    )
    print(json.dumps({
        "status": "ok",
        "storyboard": args.storyboard,
        "output": str(output_path),
        "sceneCount": len(scenes),
        "resolution": f"{width}x{height}",
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
