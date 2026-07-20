---
name: cinematic_ink_webtoon_v1
scope: acc1_video_candidate
status: local_style_candidate_pending_pilot_approval
canvas:
  width: 1920
  height: 1080
  fps: 30
colors:
  midnight_navy: "#101A2C"
  deep_teal: "#174B52"
  warm_amber: "#D49345"
  coral: "#D76558"
  ivory: "#F1E7D3"
  vermilion: "#A83E31"
  charcoal: "#24252A"
type:
  display: "Roboto Condensed, Arial Narrow, Arial, sans-serif"
  body: "Inter, Arial, sans-serif"
  subtitle: "Inter, Arial, sans-serif"
visual_mix:
  fullscreen_cinematic: 50
  unequal_panel_pages: 30
  evidence_objects: 15
  brand_transitions: 5
image_budget:
  unique_illustrations_per_story: [16, 20]
  visual_state_seconds: [6, 10]
text_policy: deterministic_html_svg_only
mascot_policy: identity_intro_cta_transition_outro_only
reference: "docs/assets/acc1-cinematic-ink-webtoon-styleframe-v1.png"
---

# ChonkerTalks — Cinematic Ink Webtoon

Этот файл — краткий машинно-читаемый визуальный контракт для новых видео
`acc1`. Подробные правила находятся в
[`docs/acc1-cinematic-ink-webtoon-v1.md`](docs/acc1-cinematic-ink-webtoon-v1.md).

## Образ

Взрослый цветной веб-комикс: современная чистая композиция и выразительные
лица сочетаются с живой тушевой линией, гуашью и фактурой бумаги. Пропорция
характера — примерно 75% современного cinematic webtoon и 25% ручной фактуры.
Это не детский комикс, не супергеройский pop-art, не чёрно-белая манга, не
глянцевый romance-manhwa и не фотореалистичная AI-реконструкция.

## Кадр и текст

- Основной ритм: полноэкранная иллюстрация сменяется страницей из 2–3
  неравных панелей; одинаковая сетка не повторяется механически.
- Полный рассказ звучит в озвучке. На изображении остаются только заголовок,
  роль, дата, сумма, короткое сообщение или ключевая фраза в 3–8 слов.
- Весь точный текст, субтитры и интерфейсы набираются HTML/SVG после генерации.
  Псевдотекст внутри AI-иллюстрации запрещён.
- Маскот не участвует в реконструкции истории: он появляется только в
  айдентике, интро, переходах, CTA и аутро.

## Движение

Страница сначала читается целиком, затем камера следует за смыслом рассказа:
обзор → плавный наезд на панель → возврат → переход к следующей панели →
финальный обзор или match cut. Движение подчинено реплике, а не таймеру.
Разрешены лёгкий параллакс, свет, вода, экран телефона и движение документов;
лица и руки не деформируются.
