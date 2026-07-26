---
name: acc1_format_visual_system_v3
scope: acc1_current_creative_reference
status: approved_creative_direction_local_mp4_verified
canvas:
  width: 1920
  height: 1080
  fps: 30
colors:
  ivory: "#F1E7D3"
  charcoal: "#24252A"
  muted_olive: "#626352"
  dusty_rose: "#9B7479"
  burgundy: "#633C46"
  deep_navy: "#172231"
  cool_lavender: "#7A718B"
  desaturated_teal: "#58787A"
type:
  display: "Roboto Condensed, Arial Narrow, Arial, sans-serif"
  body: "Inter, Arial, sans-serif"
  subtitle: "Inter, Arial, sans-serif"
formats:
  BUNDLE: separate_story_character_locks_with_shared_episode_grammar
  SAGA: continuous_cast_panorama_and_discovery_panels
  THREAD: prompt_anchor_with_distinct_response_vignettes
image_budget:
  unique_illustrations_per_story: [16, 20]
  visual_state_seconds: [6, 10]
text_policy: deterministic_html_svg_only
mascot_policy: identity_intro_cta_transition_outro_only
references:
  BUNDLE: "docs/assets/acc1-format-visual-system-v3/bundle-relationships-v1.png"
  SAGA: "docs/assets/acc1-format-visual-system-v3/saga-strange-v1.png"
  THREAD: "docs/assets/acc1-format-visual-system-v3/thread-confessions-v1.png"
---

# ChonkerTalks — Format Visual System v3

Этот файл — краткий машинно-читаемый визуальный контракт для новых видео
`acc1`. Подробные правила находятся в
[`docs/acc1-format-visual-system-v3.md`](docs/acc1-format-visual-system-v3.md).

## Образ

Взрослый рисованный графический роман: выразительные лица, стабильные герои,
живая линия, мягкий сел-шейдинг, гуашь и бумажная фактура. Формат определяет
структуру страницы, а тема — палитру и ритм. Фотографии, фотоколлаж,
фотореалистичная AI-реконструкция и оранжевый универсальный шаблон запрещены.

## Кадр и текст

- `BUNDLE`: отдельные мини-комиксы с разными героями внутри одной темы.
- `SAGA`: один непрерывный состав героев, панорамы и панели открытий.
- `THREAD`: один вопрос и разные портреты/сцены ответов в i-flow.
- Одинаковая сетка и одна реакционная карточка не повторяются механически.
- Полный рассказ звучит в озвучке. На изображении остаются только заголовок,
  роль, дата, сумма, короткое сообщение или ключевая фраза в 3–8 слов.
- Весь точный текст, субтитры и интерфейсы набираются HTML/SVG после генерации.
  Псевдотекст внутри AI-иллюстрации запрещён.
- Маскот не участвует в реконструкции истории: он появляется только в
  айдентике, интро, переходах, CTA и аутро.

## Движение

Страница сначала читается целиком, затем камера следует за смыслом рассказа:
обзор → герой/взаимодействие/деталь → смысловая пауза или панорама → match cut
или мягкий переход. Обязательного возврата и одинакового цикла нет. Движение
подчинено реплике, а не таймеру.
Разрешены лёгкий параллакс, свет, вода, экран телефона и движение документов;
лица и руки не деформируются.
