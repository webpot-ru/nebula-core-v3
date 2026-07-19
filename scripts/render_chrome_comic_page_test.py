#!/usr/bin/env python3
"""Render the two-page comic test through local Google Chrome and FFmpeg.

This is intentionally lightweight: Chrome captures deterministic JPEG camera
positions at the final 30 fps. JPEG frames keep the temporary cache small enough
for a MacBook while avoiding visible camera steps. The optional packaging mode
adds deterministic Russian intro, CTA and outro cards without any image call.
No audio, server, Node runtime, MotionCanvas, provider call or publication is
involved here.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from render import (
    RenderError,
    find_browser_binary,
    find_ffmpeg_binary,
    start_cdp_browser,
    stop_browser,
)


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#171714}
#stage{position:relative;width:1920px;height:1080px;overflow:hidden;background:#1b1b18}
.page{position:absolute;inset:0;background:#181815;opacity:0;transform:scale(1.03);will-change:transform,opacity}
.page img{width:100%;height:100%;object-fit:cover;display:block}
.vignette{position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at center,transparent 57%,rgba(13,13,11,.23) 100%)}
#flash{position:absolute;inset:0;background:#f3ead8;opacity:0;pointer-events:none}
.copy-card{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:120px 210px;opacity:0;pointer-events:none;color:#f6eddb;text-shadow:0 3px 18px rgba(0,0,0,.48);will-change:opacity}
.copy-card:before{content:"";position:absolute;inset:0;background:rgba(18,24,18,.66);z-index:-1}
.copy-kicker{font:700 25px/1 Arial,sans-serif;letter-spacing:.24em;color:#efc784;margin-bottom:26px}
.copy-main{font:800 66px/1.1 Arial,sans-serif;letter-spacing:.035em;max-width:1200px}
.copy-sub{font:500 30px/1.3 Arial,sans-serif;letter-spacing:.02em;max-width:980px;margin-top:28px}
#cta .copy-main{font-size:52px}.cta-line{height:4px;width:136px;background:#d57c48;margin:30px auto 0}
</style></head><body data-render-ready="true">
<div id="stage"><div id="p1" class="page"><img src="pages/work-page-01-arrival.png"></div><div id="p2" class="page"><img src="pages/work-page-02-choice.png"></div><div id="intro" class="copy-card"><div class="copy-kicker">ИСТОРИЯ ИЗ ОФИСА</div><div class="copy-main">НОВАЯ РАБОТА.<br>СТРАННЫЙ ПОДАРОК.<br>ОДИН ВОПРОС.</div><div class="copy-sub">Что бы сделали вы?</div></div><div id="cta" class="copy-card"><div class="copy-kicker">ПРОДОЛЖЕНИЕ ИСТОРИИ</div><div class="copy-main">ЕСЛИ ИСТОРИЯ ЗАЦЕПИЛА —<br>ПОСТАВЬ ЛАЙК И ПОДПИШИСЬ.</div><div class="cta-line"></div><div class="copy-sub">Так ты не пропустишь следующую.</div></div><div id="outro" class="copy-card"><div class="copy-kicker">ТВОЙ ВЫБОР</div><div class="copy-main">ТЫ БЫ ПРОМОЛЧАЛ(А)<br>ИЛИ РАССКАЗАЛ(А)?</div><div class="copy-sub">Напиши в комментариях. Подпишись, если хочешь следующую историю.</div></div><div id="flash"></div><div class="vignette"></div></div>
<script>
const p1=document.getElementById('p1'), p2=document.getElementById('p2'), flash=document.getElementById('flash');
const intro=document.getElementById('intro'), cta=document.getElementById('cta'), outro=document.getElementById('outro');
const WITH_PACKAGING=__WITH_PACKAGING__;
function ease(x){return x<.5?2*x*x:1-Math.pow(-2*x+2,2)/2}
function fade(t,start,end,edge=.35){return Math.max(0,Math.min(1,Math.min((t-start)/edge,(end-t)/edge,1)))}
function camera(el, x,y,scale){el.style.transform=`translate(${x}px,${y}px) scale(${scale})`;}
window.renderComicAt = (t) => {
  if(WITH_PACKAGING){
    const p1Progress=Math.max(0,Math.min(1,(t-4)/6)), p1Ease=ease(p1Progress);
    const p2Progress=Math.max(0,Math.min(1,(t-13)/6)), p2Ease=ease(p2Progress);
    camera(p1,-72*p1Ease,-24*p1Ease,1.045+.13*p1Ease);
    camera(p2,54*(1-p2Ease),-30*(1-p2Ease),1.18-.10*p2Ease);
    p1.style.opacity=t < 13 ? '1' : '0'; p2.style.opacity=t < 13 ? '0' : '1';
    intro.style.opacity=fade(t,0,4).toFixed(3);
    cta.style.opacity=fade(t,10,13).toFixed(3);
    outro.style.opacity=fade(t,19,22).toFixed(3);
    const boundary=Math.max(0,1-Math.abs(t-13)/.20); flash.style.opacity=boundary.toFixed(3);
    return {mode:'packaging',t};
  }
  const page=Math.min(1,Math.floor(t/5)), local=(t%5)/5, e=ease(local);
  const secondProgress=Math.max(0,Math.min(1,(t-4.72)/5.28)), secondEase=ease(secondProgress);
  camera(p1, -72*Math.min(1,t/5), -24*Math.min(1,t/5), 1.045+.13*Math.min(1,t/5));
  camera(p2, 54*(1-secondEase), -30*(1-secondEase), 1.18-.10*secondEase);
  p1.style.opacity=t < 5 ? '1' : '0'; p2.style.opacity=t < 5 ? '0' : '1';
  const boundary=Math.max(0,1-Math.abs(t-5)/.20); flash.style.opacity=boundary.toFixed(3);
  intro.style.opacity='0';cta.style.opacity='0';outro.style.opacity='0';
  return {page,local};
};
</script></body></html>"""


def write_html(output_dir: Path, *, with_packaging: bool) -> Path:
    path = output_dir / "index.html"
    path.write_text(HTML.replace("__WITH_PACKAGING__", "true" if with_packaging else "false"), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--with-packaging", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    page_files = [
        output_dir / "pages/work-page-01-arrival.png",
        output_dir / "pages/work-page-02-choice.png",
    ]
    missing = [str(item) for item in page_files if not item.exists()]
    if missing:
        raise RuntimeError("missing generated comic pages: " + ", ".join(missing))
    html = write_html(output_dir, with_packaging=args.with_packaging)
    frames_dir = output_dir / "capture-frames"
    if frames_dir.exists():
        raise RuntimeError(
            f"refusing to overwrite existing capture frames: {frames_dir}; "
            "move the prior test to project Trash first"
        )
    frames_dir.mkdir(parents=True)

    browser = find_browser_binary()
    process, client = start_cdp_browser(browser, output_dir, 1920, 1080)
    duration = 22.0 if args.with_packaging else 10.0
    fps_capture = 30
    timestamps = [index / fps_capture for index in range(int(duration * fps_capture))]
    try:
        client.command("Page.navigate", {"url": html.as_uri()}, timeout=10)
        for index, timestamp in enumerate(timestamps):
            evaluated = client.command("Runtime.evaluate", {
                "expression": f"window.renderComicAt({timestamp:.6f})",
                "returnByValue": True,
            }, timeout=5)
            if evaluated.get("exceptionDetails"):
                raise RenderError("comic page animation JavaScript failed")
            screenshot = client.command("Page.captureScreenshot", {
                "format": "jpeg", "quality": 84,
                "fromSurface": True, "captureBeyondViewport": False,
            }, timeout=15)
            data = screenshot.get("data")
            if not isinstance(data, str):
                raise RenderError(f"Chrome did not return frame {index + 1}")
            (frames_dir / f"frame_{index:04d}.jpg").write_bytes(base64.b64decode(data))
    finally:
        client.close()
        stop_browser(process)

    concat = frames_dir / "frames.ffconcat"
    lines = ["ffconcat version 1.0"]
    for index in range(len(timestamps)):
        lines.extend([f"file 'frame_{index:04d}.jpg'", f"duration {1 / fps_capture:.6f}"])
    lines.append(f"file 'frame_{len(timestamps) - 1:04d}.jpg'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        find_ffmpeg_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
        "-movflags", "+faststart", "-t", f"{duration:.3f}", str(output),
    ]
    import subprocess
    subprocess.run(command, check=True)
    report = {
        "renderer": "local_google_chrome_cdp_plus_ffmpeg",
        "audio": False,
        "duration_sec": duration,
        "capture_fps": fps_capture,
        "output_fps": 30,
        "frames": len(timestamps),
        "with_packaging": args.with_packaging,
        "output": output.name,
    }
    (output_dir / "render-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
