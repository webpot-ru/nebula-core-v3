#!/usr/bin/env python3
"""Render a no-provider visual approval preview for acc1 style v2."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from render import (
    RenderError,
    find_browser_binary,
    start_cdp_browser,
    stop_browser,
)

DEFAULT_PAGE = ROOT / "build/chrome-comic-page-test/pages/work-page-01-arrival.png"
INTRO = ROOT / "videos/chonker-talks-intro/renders/chonker-talks-editorial-intro-preview-v2.mp4"
CTA = ROOT / "videos/chonker-talks-cta/renders/chonker-talks-midroll-cta-v2.webm"
OUTRO = ROOT / "videos/chonker-talks-outro/renders/chonker-talks-youtube-outro-v1.mp4"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def write_ass(path: Path) -> None:
    path.write_text(
        """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,46,&H00F5F2EA,&H000000FF,&H00101010,&H00101010,-1,0,0,0,100,100,0,0,1,2,0,5,110,110,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\pos(960,1015)}На новой работе меня ждал странный подарок.
Dialogue: 0,0:00:02.00,0:00:04.00,Default,,0,0,0,,{\\pos(960,1015)}Начальник молча поставил часы на стол.
Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,{\\pos(960,1015)}Я не понимала, почему он следит за временем.
Dialogue: 0,0:00:06.00,0:00:08.00,Default,,0,0,0,,{\\pos(960,1015)}Тогда я заметила стрелку на циферблате.
Dialogue: 0,0:00:08.00,0:00:10.00,Default,,0,0,0,,{\\pos(960,1015)}И всё наконец встало на свои места.
""",
        encoding="utf-8",
    )


def render_semantic_story(page: Path, output_dir: Path, output: Path) -> None:
    html = output_dir / "semantic-camera-preview.html"
    html.write_text(
        f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#090b0f}}
#stage{{position:relative;width:1920px;height:1080px;overflow:hidden;background:#090b0f}}
#comic{{position:absolute;left:0;top:0;width:1920px;height:1080px;transform-origin:0 0;will-change:transform}}
#comic img{{width:1920px;height:1080px;display:block}}
#band{{position:absolute;left:0;top:950px;width:1920px;height:130px;background:rgba(9,11,15,.94);display:flex;align-items:center;justify-content:center;padding:0 110px}}
#subtitle{{font:700 46px/1 Arial,sans-serif;color:#f5f2ea;text-align:center;white-space:nowrap;text-shadow:-2px -2px 0 #101010,2px -2px 0 #101010,-2px 2px 0 #101010,2px 2px 0 #101010}}
</style></head><body data-render-ready="true"><div id="stage"><div id="comic"><img src="{page.as_uri()}"></div><div id="band"><div id="subtitle"></div></div></div>
<script>
const comic=document.getElementById('comic'), subtitle=document.getElementById('subtitle');
const shots=[
  {{s:0,e:1.5,a:[0,0,1],b:[-18,-7,1.025],text:'На новой работе меня ждал странный подарок.'}},
  {{s:1.5,e:4.0,a:[-18,-7,1.025],b:[-92,-34,1.12],text:'Начальник молча поставил часы на стол.'}},
  {{s:4.0,e:6.5,a:[-92,-34,1.12],b:[-800,-340,1.60],text:'Тогда я заметила стрелку на циферблате.'}},
  {{s:6.5,e:9.0,a:[-800,-340,1.60],b:[-895,-535,1.45],text:'И поняла, почему он следит за временем.'}},
  {{s:9.0,e:10.0,a:[-895,-535,1.45],b:[-120,-55,1.16],text:'Теперь всё встало на свои места.'}}
];
function ease(x){{return x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2}}
window.renderAt=(t)=>{{
  const shot=shots.find(x=>t>=x.s&&t<x.e)||shots[shots.length-1];
  const p=ease(Math.max(0,Math.min(1,(t-shot.s)/(shot.e-shot.s))));
  const x=shot.a[0]+(shot.b[0]-shot.a[0])*p;
  const y=shot.a[1]+(shot.b[1]-shot.a[1])*p;
  const z=shot.a[2]+(shot.b[2]-shot.a[2])*p;
  comic.style.transform=`translate3d(${{x.toFixed(4)}}px,${{y.toFixed(4)}}px,0) scale(${{z.toFixed(6)}})`;
  subtitle.textContent=shot.text;
  return {{t,x,y,z,text:shot.text}};
}};
</script></body></html>""",
        encoding="utf-8",
    )
    frames_dir = output_dir / "semantic-camera-frames"
    if frames_dir.exists():
        for item in frames_dir.glob("frame_*.png"):
            item.unlink()
    frames_dir.mkdir(parents=True, exist_ok=True)
    process, client = start_cdp_browser(find_browser_binary(), output_dir, 1920, 1080)
    frame_count = 300
    try:
        client.command("Page.navigate", {"url": html.as_uri()}, timeout=10)
        for index in range(frame_count):
            timestamp = index / 30
            evaluated = client.command("Runtime.evaluate", {
                "expression": f"window.renderAt({timestamp:.6f})", "returnByValue": True,
            }, timeout=5)
            if evaluated.get("exceptionDetails"):
                raise RenderError("semantic camera JavaScript failed")
            screenshot = client.command("Page.captureScreenshot", {
                "format": "png", "fromSurface": True, "captureBeyondViewport": False,
            }, timeout=15)
            data = screenshot.get("data")
            if not isinstance(data, str):
                raise RenderError(f"Chrome did not return semantic frame {index + 1}")
            (frames_dir / f"frame_{index:04d}.png").write_bytes(base64.b64decode(data))
    finally:
        client.close()
        stop_browser(process)
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "30",
        "-i", str(frames_dir / "frame_%04d.png"), "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", "10", str(output),
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--page", default=str(DEFAULT_PAGE))
    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    page = Path(args.page).resolve()
    required = [page, INTRO, CTA, OUTRO]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing preview assets: " + ", ".join(missing))

    story = output_dir / "webtoon-motion-with-subtitles.mp4"
    render_semantic_story(page, output_dir, story)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Cold open (2s) -> real intro -> comic continuation with the real CTA
    # keyed over it -> real outro. Audio is deliberately omitted: this gate
    # approves composition and motion before any AI33 call.
    final_filter = (
        "[0:v]trim=0:2,setpts=PTS-STARTPTS[v0];"
        "[1:v]scale=1920:1080,fps=30,format=yuv420p,setpts=PTS-STARTPTS[v1];"
        "[0:v]trim=2:10,setpts=PTS-STARTPTS[v2];"
        "[0:v]trim=4:8,setpts=PTS-STARTPTS[v3];"
        "[v0][v1][v2][v3]concat=n=4:v=1:a=0,"
        "drawbox=x=0:y=950:w=1920:h=130:color=0x090b0f@1:t=fill:enable='between(t,8,11)'[base];"
        "[2:v]scale=1920:1080,fps=30,colorkey=0x000000:0.11:0.08,"
        "format=yuva420p,setpts=PTS-STARTPTS+8/TB[cta];"
        "[base][cta]overlay=0:0:eof_action=pass:format=auto[withcta];"
        "[3:v]scale=1920:1080,fps=30,format=yuv420p,setpts=PTS-STARTPTS[v4];"
        "[withcta][v4]concat=n=2:v=1:a=0[v]"
    )
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(story), "-i", str(INTRO), "-i", str(CTA), "-i", str(OUTRO),
        "-filter_complex", final_filter, "-map", "[v]", "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-movflags", "+faststart", str(output),
    ])
    report = {
        "status": "READY_FOR_VISUAL_APPROVAL",
        "style_id": "chonker_cinematic_webtoon_v2",
        "renderer_id": "chrome_guided_webtoon_v2_preview",
        "provider_calls": 0,
        "audio": False,
        "output": output.name,
        "sha256": sha256_file(output),
        "publication_authorized": False,
    }
    (output_dir / "preview-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
