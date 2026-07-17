# План внедрения cinematic-формата acc1 — 2026-07-16

Статус: этапы A-C, техническая часть этапа D и локальная инфраструктура
post-human release gate реализованы 2026-07-17 поверх актуального
`origin/main@8c5eb7d`. `reddit_pages` остаётся дефолтом; человеческий
creative/audio review и production canary ещё не выполнялись.

## Решение

В `acc1` нужно добавить второй, явно именованный режим длинного видео:
`cinematic_story_v1`. Он использует полноэкранные сюжетные изображения,
медленное движение виртуальной камеры и голос как главный носитель истории.

Существующий режим с Reddit-страницами слева и медным Chonker справа остаётся
отдельным совместимым контрактом. Новый режим не становится дефолтом, пока не
пройдёт детерминированный render/QA, сравнение на одном и том же выпуске и
человеческий creative review.

Формат не ограничивается хоррором. Визуальный и голосовой тон выбирается из
пяти действующих pillars `acc1`; события, концовка, truth mode и источник
по-прежнему определяются текущей стратегией канала.

Исследовательская база и вывод о том, почему обычный выпуск Mr. Nightmare, а
не годовой спецвыпуск, является рабочим визуальным ориентиром, находятся в
[`russian-longform-competitor-analysis-2026-07-11.md`](russian-longform-competitor-analysis-2026-07-11.md).

## Что уже есть

Проект уже умеет:

- собирать source-bound сценарий и сюжетные beats;
- назначать отдельные роли основного рассказчика и комментариев;
- запрашивать `eleven_v3`, сохранять задачи и проверять реальную длительность
  и word timings;
- генерировать и checksum-bind сюжетные изображения;
- строить 16:9 storyboard, объединять проверенную озвучку с MP4 и запускать
  fail-closed media QA.

Локально реализовано:

- отдельный явный `cinematic_story_v1` с полноэкранным движением неподвижных
  изображений и неизменным baseline `reddit_pages`;
- checksum-bound shot plan и caption/SRT sidecars поверх принятого image plan;
- пять pillar-aware профилей исполнения без автоматической смены voice ID;
- semantic chunks, отдельная pause map и voice-only mix с измеренным loudness;
- manifest v2 и сквозные mode/profile/pause/mix/shot bindings при строгой
  совместимости исторического manifest v1;
- mode-aware storyboard, renderer, factory, workflow, creative template и
  fail-closed media QA;
- локальная no-network comparison fixture для одинакового сценария и одного
  финального audio hash в baseline/cinematic вариантах.

Внешними воротами остаются человеческий creative/audio review точного
кандидата, отдельно подтверждённый provider/GitHub canary, реальный правовой
допуск источника и точное разрешение на YouTube upload. Factory-aware release
adapter, rights-manifest contract и no-provider GitHub gate уже реализованы
локально, но не могут заменить реальные доказательства и не были запущены.

## Локальное доказательство — 2026-07-17

Production-функции, слитые трёхсторонне с актуальными OpenAI Flex/resume
изменениями `main`, собрали один синтетический SAGA-кандидат в двух режимах в
`/tmp/acc1-cinematic-comparison-main-20260717`. Тест
`tests.test_acc1_cinematic_fixture` завершился за `20.348s` со статусом `OK`;
перед ним 224 целевых теста прошли за исключением двух устаревших тестовых
вызовов интерфейса, после точечной коррекции оба повторно завершились `OK`.
Оба варианта прошли `compilation_qa.run_qa` и содержат реальные 1920×1080,
H.264/AAC, 30 fps MP4:

- baseline: `modes/reddit_pages/final-output.mp4`, SHA-256
  `fdfc03148b91fa0aabf301d4de0f5aa00a7117ee440e7219f05e9bac657cd2dd`;
- cinematic: `modes/cinematic_story_v1/final-output.mp4`, SHA-256
  `f98c20c8c8adabc453f5c9df52f84b8950f09b831f55da0b65e44d4a7b821fe2`;
- comparison report self-hash:
  `af329ebd0bd2818ab8df431faa19be73b84695017fc3ee18d7c1055592ed15e8`.

Инварианты доказаны машинно: один source/body hash, один narration/timing
contract, одни raw WAV chunks и одинаковый финальный voice-only WAV
`0db0f81f8d8665a8abf0a1eab512b959114d636ea0fedef89d98418deb7dfd05`.
При этом episode-plan, pause-map и audio-mix sidecar у режимов разные и
mode-bound. Оба mix report измерили `-16.0 LUFS` и `-14.91 dBTP`. Кадры intro,
начала/середины/конца story, outro и baseline просмотрены из итоговых MP4;
service labels не перекрываются, story-кадр остаётся чистым, а slow push/pan
виден между началом и серединой.

Fixture использует синтетическую геометрию и WAV-тоны. Поэтому его технический
статус — `PASS`, но общий статус намеренно остаётся
`BLOCKED_PENDING_HUMAN`: он не доказывает качество реального narrator voice,
provider-изображений, source rights или зрительского creative verdict.

## Целевой зрительский контракт

### Изображение

- Основная часть истории показывается полноэкранными сюжетными сценами, а не
  длинной Reddit-карточкой.
- Одно базовое изображение может давать несколько виртуальных кадров:
  приближение, аккуратное боковое смещение или смену точки кадрирования. Это
  повышает визуальный ритм без дополнительного provider-вызова.
- Обычный кадр держится ориентировочно 20–45 секунд. Смена происходит на
  смысловом повороте, смене места или появлении нового участника, а не на
  каждом предложении.
- Движение остаётся почти незаметным: типичный zoom начинается около исходного
  масштаба и заканчивается в пределах примерно 106–110%. Панорама допускается
  только внутри безопасной композиции.
- Между историями используется короткая чистая заставка. Постоянный крупный
  талисман не должен закрывать сюжетную сцену; Chonker остаётся небольшим
  узнаваемым brand anchor там, где это действительно помогает.
- Полный текст истории не печатается поверх изображения. Источник и truth mode
  показываются в начале/переходе и сохраняются в метаданных. На экране можно
  оставлять только короткий хук, ключевую реплику или поворот.
- Полная доступность обеспечивается отдельной caption-дорожкой, построенной из
  уже проверенных word timings. Burned-in подписи остаются короткими и
  необязательными.

### Распределение по форматам

- `SAGA` — основной кандидат для `cinematic_story_v1`: одна длинная история,
  расширенный набор базовых сцен и несколько виртуальных кадров на сцену.
- `BUNDLE` — cinematic допустим, но каждая история получает самостоятельный
  мини-набор сцен, а общий image budget остаётся ограниченным и заранее
  подтверждённым.
- `THREAD` — сохраняет response/card-представление. Полноэкранный cinematic
  может использоваться только для вступления и переходов, потому что
  различимость отдельных ответов важнее атмосферного кадра.

Точное количество provider-изображений принадлежит image plan и spend lease.
Shot plan не имеет права скрыто увеличивать число генераций: новые движения и
кадрирования строятся локально из уже принятых файлов.

## Контракт озвучки

### Голосовые роли

- Сохраняется один постоянный мужской голос канала.
- Женский голос используется только для подтверждённых comment/response
  сегментов. Кавычки или неатрибутированный диалог не переключают голос.
- Новый cinematic-режим не меняет voice ID автоматически. Сначала настраивается
  исполнение существующего голоса, затем отдельным решением оценивается
  необходимость замены.

### Профили исполнения

Episode plan должен объявлять `narration_profile_id`, выбранный по pillar:

- отношения/семья — тёплая разговорная подача;
- работа/деньги/справедливость — ясная и чуть более собранная;
- признания/неловкое/табу — близкая и доверительная;
- профессии/человеческий опыт — спокойная наблюдательная;
- странное/тёмное/необъяснимое — сдержанная, медленнее и с большим воздухом.

Профиль определяет допустимый диапазон скорости, пауз и provider voice settings,
но не переписывает текст и не добавляет эмоции, которых нет в источнике.
Конкретные значения должны храниться в кодовом контракте, а не копироваться
между документами.

### Сегменты и паузы

- TTS-чанки формируются по утверждённым story beats и естественным абзацам, а
  не только по пределу символов.
- Паузы добавляются отдельной timeline/mix-операцией, а не многоточиями и
  искусственной пунктуацией в source-bound narration.
- Короткая пауза разделяет фразы, более заметная — новый beat, а переход между
  историями получает отдельный музыкальный или тихий интервал.
- Склейка не должна менять тембр, громкость или комнатное ощущение между
  соседними чанками.

### Финальный микс

- Голос остаётся самым громким и разборчивым слоем.
- Первый cinematic-пилот проходит voice-only baseline. Музыка и SFX
  подключаются только после того, как сам голос проходит review.
- Если используется атмосферный слой, он должен быть собственным или
  лицензированным, checksum-bound и заметно тише речи. Он не может маскировать
  согласные, паузы или концовку фразы.
- Целевой технический ориентир для финального файла: согласованная громкость
  около `-16 LUFS` с допуском в один LU и true peak не выше `-1.5 dBTP`.
  Точные измеренные значения записываются в audio mix report.

## Изменения по слоям проекта

### 1. Контракт эпизода

Добавить в episode/creative manifest явные поля `visual_mode`,
`narration_profile_id`, shot-plan binding и audio-mix binding. Неизвестный режим
или профиль должен блокировать production. Старые артефакты продолжают
валидироваться по своему объявленному контракту.

Основной владелец правил: episode plan/manifest и
[`acc1_visual_contract.py`](../acc1_visual_contract.py).

### 2. Scene и shot planning

Текущий image plan остаётся источником базовых файлов. Поверх него появляется
детерминированный shot plan: границы beat, выбранный asset, тип движения,
начальная/конечная область кадрирования и переход. Каждый shot checksum-bound и
полностью воспроизводим без сети.

Основные владельцы: [`acc1_episode_images.py`](../acc1_episode_images.py) и
[`compilation_storyboard.py`](../compilation_storyboard.py).

### 3. Cinematic renderer

Добавить отдельную render-ветку, которая строит полноэкранное движение из
локальных принятых изображений и не меняет существующий Reddit/Chonker путь.
Рендерер должен сохранять 1920×1080, 30 fps, точное покрытие narration audio,
проверку хэшей и запрет внешних загрузок.

Основной владелец: [`compilation_renderer.py`](../compilation_renderer.py).

### 4. Narration и mix

Сделать semantic chunking, profile-aware TTS request contract, отдельную pause
map и локальную сборку финального voice/mix файла. Provider task identity,
resume-защита и word timings должны сохраниться без ослабления.

Основные владельцы: [`compilation_narration.py`](../compilation_narration.py) и
[`compilation_tts_runner.py`](../compilation_tts_runner.py).

### 5. Factory и QA

Factory должен передавать объявленный режим через весь evidence chain, но не
выбирать cinematic скрытым fallback. QA проверяет shot coverage, диапазон
движения, отсутствие случайных смен, audio coverage, loudness report, voice
roles и точную привязку к episode plan.

Основные владельцы: [`acc1_episode_factory.py`](../acc1_episode_factory.py),
[`compilation_qa.py`](../compilation_qa.py) и
[`acc1-visual-qa-checklist.md`](acc1-visual-qa-checklist.md).

## Порядок внедрения

### Этап A — контракты без нового MP4

1. Ввести именованные visual/narration modes и fail-closed валидацию.
2. Добавить shot-plan schema и детерминированные тестовые fixtures.
3. Доказать, что старый renderer и существующие manifests проходят без
   изменения результата.

Готовность: targeted unit tests и неизменный readback старого fixture.

### Этап B — no-spend cinematic render

1. Использовать локальные fixture-изображения и синтетическую/существующую
   озвучку.
2. Реализовать полноэкранный zoom/pan и переходы.
3. Проверить начало, середину, переход между историями и финал по реальным
   кадрам MP4.

Готовность: воспроизводимый 16:9 H.264/AAC artifact, storyboard/render report и
mode-aware QA без внешних вызовов.

### Этап C — озвучка и микс

1. Привязать semantic chunks и pause map к тем же beats.
2. Сначала собрать новый mix из уже существующего narration audio.
3. Только после этого, по отдельному подтверждению платного scope, сделать
   короткий образец существующим narrator voice с новым профилем.

Готовность: voice continuity PASS, измеренный loudness report, отсутствие
обрезанных слов и расхождения audio/video timeline.

### Этап D — сравнение одного выпуска

Один immutable episode candidate рендерится двумя способами с одинаковым
сценарием и одинаковой озвучкой:

1. текущий Reddit/Chonker baseline;
2. `cinematic_story_v1`.

Creative review сравнивает первые 30 секунд, понятность источника, усталость от
экрана, соответствие сцен тексту, качество голоса и ощущение целостного
бренда. Новый режим не проходит по субъективному «красивее»; нужны точные
таймкоды и решение `PASS`, `CHANGE` или `BLOCKED`.

### Этап E — production canary

После локального PASS нужен отдельно разрешённый provider scope, затем
artifact-only GitHub run. Private/unlisted YouTube canary возможен только после
действующего release-gate adapter, правового допуска конкретных источников,
human review и точного upload approval.

Локальная инфраструктура этих ворот реализована 2026-07-17: factory-aware
`acc1_release_gate.py`, точный `acc1_rights_manifest.py`, no-provider
`acc1_release_review.yml` и private-only `acc1_private_upload.yml`. Private
upload больше не может доверять одному `READY_FOR_HUMAN_REVIEW`: он требует
отдельную self-hashed квитанцию `READY_FOR_PRIVATE_REVIEW`, связанную с точным
factory run, видео, аудио, thumbnail, human review и rights evidence. Это
локальная готовность к этапу, а не его прохождение: реального rights record,
human PASS, GitHub canary или YouTube upload/readback ещё нет.

Live readback 2026-07-17 показал отдельный deployment-риск: на GitHub `main`
активен старый manual workflow `acc1 Private Artifact Upload` id `313326356`,
который ещё принимает один `READY_FOR_HUMAN_REVIEW`; новый `acc1 Release
Review Gate` там не зарегистрирован. Старый workflow нельзя запускать до merge
новой цепочки либо его отдельно разрешённого отключения.

## Ворота продвижения в дефолт

`cinematic_story_v1` может заменить baseline для SAGA/BUNDLE только когда:

1. старый режим не сломан и остаётся воспроизводимым;
2. no-spend fixture и полный candidate проходят технический QA;
3. cinematic-вариант получает человеческий `PASS`;
4. голос и mix проходят отдельный audio review;
5. первый разрешённый YouTube-пилот получает реальный retention/readback и не
   проигрывает сопоставимому long-form baseline;
6. изменение дефолта отдельно зафиксировано в `channels.json` и документации.

Один outlier конкурента или один красивый локальный ролик не является
достаточным основанием.

## Live implementation status — 2026-07-17

PR [#44](https://github.com/webpot-ru/nebula-core-v3/pull/44) merged the
feature-flagged cinematic implementation and factory-aware release chain to
`main@017934e3`. The first authorized artifact-only canary
[`29555487790`](https://github.com/webpot-ru/nebula-core-v3/actions/runs/29555487790)
stopped before every paid provider because deterministic source review found
only one eligible candidate out of four. The saved queue proved one rejection
was a classifier false positive: a final Reddit author-profile attribution was
treated like a part-2 dependency. The corrected contract allows only exact
Reddit `/user/` and `/u/` attribution links, keeps every continuation/external
link and image blocked. Canary `29557578785` then found exactly five valid
stories at depth 50 and reached paid production, where one Flex response
completed before an explicit capacity HTTP 429 stopped the next request.
Those five sources are now correctly reserved, so sustainable episode rotation
uses one maximum-size Reddit listing page (100 rows) under the unchanged HTTP
cap. Source-only run `29558815654` proved that path with five new, reservation-
disjoint finalists. Paid run `29559053073` then passed the new source lease but
received the same explicit Flex-capacity HTTP 429 on its first OpenAI request;
image, AI33, render, and YouTube were not reached. Because this is the second
independent Flex-capacity failure, PR #45 adds an explicit `default` service-tier
canary path while retaining Flex as the default and prohibiting automatic
fallback. The selected tier is hash-bound through preflight, lease, request,
journal, and response readback. A fresh standard-tier artifact-only canary is
still required; promotion to the default still requires the technical, human,
audio, rights and retention gates above.

## Результат первого implementation slice

Первый локальный проход выполнен в исходных границах visual contract:

1. добавить `visual_mode` и детерминированный shot plan;
2. реализовать `cinematic_story_v1` за feature flag;
3. собрать no-spend fixture MP4;
4. добавить targeted renderer/storyboard/QA tests;
5. выполнить визуальный readback итогового MP4.

Этот slice не вызывал Reddit, OpenAI, image provider, AI33 или YouTube и не
менял `channels.json`. Voice profiles и локальный measured voice-only mix также
реализованы без provider-вызова. Платный образец существующего narrator voice
остаётся отдельным действием только после принятия визуального доказательства.

## Не входит в этот план

- копирование голоса, музыки, изображений, заставок или оформления Mr.
  Nightmare;
- автоматическое использование слова `TRUE` для непроверенных Reddit-историй;
- смена текущих voice IDs без отдельного прослушивания;
- скрытое увеличение image/TTS budget;
- изменение YouTube-брендинга, публикация или включение автоматизации;
- обещание роста просмотров до сопоставимого audience readback.
