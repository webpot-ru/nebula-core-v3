# Prompt for Code Review and Bug Fixing AI

Copy the prompt below and paste it into Claude, GPT-4, or another AI assistant to review and fix the remaining bugs in the `nebula-core-v3` project.

---

```text
You are an expert Python and Web Developer specializing in video rendering automation (Puppeteer/Playwright, FFmpeg) and API integrations (Google YouTube Data API, ElevenLabs TTS).

I have a repository called `nebula-core-v3` which is a multilingual YouTube automation pipeline. The pipeline scrapes Reddit stories, translates/voices them, renders them as MP4 videos using a local web simulator (RedditSim) in headless Chrome, and uploads them to YouTube.

We have successfully resolved and verified all YouTube OAuth credentials and scopes for all 7 channels. All tokens are verified and the project is in Production mode.

Now, I need you to review the codebase and fix the following remaining bugs and features in the video rendering and voicing pipeline:

### 1. Hide Control Panel in Recorded Videos
- **Current State:** The control panels (sidebar, buttons, HUD) are visible in the recorded video frames.
- **Goal:** Hide `#controlSidebar`, topbars, and bottom buttons when `.clean-mode` or `.render-mode` is active under `layout-desktop` or mobile layout in `style.css` and `app.js`. The final MP4 should look like a clean Reddit interface.

### 2. Implement Story & Comments Translation Step
- **Current State:** The scraper fetches stories, but we need to ensure the final story, title, body, and all comment bodies are fully translated to the target channel's language (Spanish, Russian, German, French, Portuguese, Italian) via VectorEngine Gemini before voicing.
- **Goal:** Verify that `translator_tts.py` / `scraper.py` translates the fields `title`, `body`, and the body of comments in `story_data.json` before storyboard generation and voicing. Fix any bugs in the translation module.

### 3. Fix Silent Video Output (Merge Voiceover Audio)
- **Current State:** Headless Chrome renders the visual frames, but the final output video does not have the audio narration merged correctly.
- **Goal:** Update `render.py` to correctly merge `narration.mp3` as the audio track into `final_output.mp4` using FFmpeg. Ensure that if the audio file exists, it is linked synchronously without losing quality.

### 4. Connect Karaoke Word-Highlighting to Renderer
- **Current State:** The simulator supports gold word-by-word highlights, but the renderer needs to pass the audio and transcript to trigger it.
- **Goal:** Ensure `render.py` correctly launches headless Chrome and navigates to the simulator with `&audio=narration.mp3&transcript=narration.json` or equivalent query parameters, so that the glowing karaoke highlights are synchronized with the voiceover in the captured video.

### 5. Handle AI33 Voice Timings Failure
- **Current State:** The pipeline failed with: "ERROR: AI33 did not return usable word timings for multi-voice narration."
- **Goal:** Investigate `translator_tts.py` around ElevenLabs multi-voice TTS parsing. Add fallback handling so that if word timings are missing or malformed, the pipeline does not crash, but falls back to standard voice rendering or typewriter animations safely.

Please read the codebase files:
- `index.html`, `style.css`, `app.js` (Reddit Simulator UI and typewriter/karaoke logic)
- `translator_tts.py` (Translation and TTS voicing logic)
- `render.py` (Headless Chrome capture and FFmpeg rendering)
- `scraper.py` (Reddit story scraper)

Provide the exact code fixes or refactoring needed to resolve these issues. Ensure all changes maintain backward compatibility and follow clean coding practices.
```
