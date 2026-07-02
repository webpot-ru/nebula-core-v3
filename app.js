// State Management
const state = {
  subreddit: 'r/AskReddit',
  username: 'u/StoryTeller',
  time: '5h ago',
  avatarColor: '#FF4500',
  postTitle: 'What is the creepiest thing that has ever happened to you that you still cannot explain?',
  postBody: 'It happened about ten years ago when I was home alone during a thunderstorm. I heard a knock at my window... on the second floor.',
  upvotes: '14.2k',
  commentsCount: '1.8k',
  
  // List of comments to type
  comments: [
    {
      id: 1,
      username: 'u/MidnightReader',
      time: '4h ago',
      body: 'That gave me literal chills. Did you look outside?',
      upvotes: '3.1k'
    },
    {
      id: 2,
      username: 'u/GhostHunter99',
      time: '3h ago',
      body: 'Probably a tree branch hitting the glass, but the rhythm makes it terrifying.',
      upvotes: '842'
    }
  ],

  // Animation settings
  isPlaying: false,
  typingSpeed: 60, // characters per second
  jitter: 30, // percentage variation
  punctuationDelay: 300, // ms pause
  simulateMistakes: true,
  cursorBlink: true,
  
  // Sound settings
  soundEnabled: true,
  soundProfile: 'mech-brown',
  soundVolume: 0.7,
  
  // Layout settings
  aspectRatio: 'ratio-16-9',
  layoutStyle: 'layout-desktop', // 'layout-mobile' or 'layout-desktop'
  showTopbar: false,
  showLeftSidebar: false,
  showRightSidebar: false,
  theme: 'theme-reddit-midnight',
  background: 'bg-dark-aurora',
  safeZone: 'sz-none', // 'sz-none', 'sz-shorts', 'sz-reels', 'sz-tiktok'
  cleanMode: false,
  renderSlides: []
};

// Web Audio API Context
let audioCtx = null;

// Typing Sequence State
let typingQueue = [];
let currentQueueIndex = 0;
let currentTextIndex = 0;
let typingTimeoutId = null;
let isErrorTyping = false; // flag when typing a typo

// DOM Elements
const subredditInput = document.getElementById('subredditInput');
const usernameInput = document.getElementById('usernameInput');
const timeInput = document.getElementById('timeInput');
const postTitleInput = document.getElementById('postTitleInput');
const postBodyInput = document.getElementById('postBodyInput');
const upvotesInput = document.getElementById('upvotesInput');
const commentsCountInput = document.getElementById('commentsCountInput');
const addCommentBtn = document.getElementById('addCommentBtn');
const commentsListContainer = document.getElementById('commentsListContainer');

const aspectRatioSelect = document.getElementById('aspectRatioSelect');
const layoutStyleSelect = document.getElementById('layoutStyleSelect');
const showTopbarCheckbox = document.getElementById('showTopbarCheckbox');
const showLeftSidebarCheckbox = document.getElementById('showLeftSidebarCheckbox');
const showRightSidebarCheckbox = document.getElementById('showRightSidebarCheckbox');
const themeSelect = document.getElementById('themeSelect');
const bgSelect = document.getElementById('bgSelect');
const safeZoneSelect = document.getElementById('safeZoneSelect');

const typingSpeedRange = document.getElementById('typingSpeedRange');
const typingSpeedVal = document.getElementById('typingSpeedVal');
const typingJitterRange = document.getElementById('typingJitterRange');
const typingJitterVal = document.getElementById('typingJitterVal');
const punctuationDelayRange = document.getElementById('punctuationDelayRange');
const punctuationDelayVal = document.getElementById('punctuationDelayVal');
const mistakesCheckbox = document.getElementById('mistakesCheckbox');
const cursorBlinkCheckbox = document.getElementById('cursorBlinkCheckbox');

const soundToggleCheckbox = document.getElementById('soundToggleCheckbox');
const keyboardSoundSelect = document.getElementById('keyboardSoundSelect');
const soundVolumeRange = document.getElementById('soundVolumeRange');
const soundVolumeVal = document.getElementById('soundVolumeVal');

const resetBtn = document.getElementById('resetBtn');
const playPauseBtn = document.getElementById('playPauseBtn');
const cleanModeBtn = document.getElementById('cleanModeBtn');
const canvasViewport = document.getElementById('canvasViewport');
const canvasContainer = document.getElementById('canvasContainer');
const redditCard = document.getElementById('redditCard');
const postFooter = redditCard.querySelector('.post-footer');
const desktopCenterFeed = document.getElementById('desktopCenterFeed');
const desktopLayoutWrapper = document.getElementById('desktopLayoutWrapper');

const postSubreddit = document.getElementById('postSubreddit');
const postAuthorName = document.getElementById('postAuthorName');
const postTime = document.getElementById('postTime');
const postAvatar = document.getElementById('postAvatar');
const postVotes = document.getElementById('postVotes');
const postCommentsCount = document.getElementById('postCommentsCount');

const postTitleContainer = document.getElementById('postTitleContainer');
const postTitleText = document.getElementById('postTitleText');
const postTitleCursor = document.getElementById('postTitleCursor');
const postBodyWrapper = document.getElementById('postBodyWrapper');
const postBodyText = document.getElementById('postBodyText');
const postBodyCursor = document.getElementById('postBodyCursor');
const postCommentsSection = document.getElementById('postCommentsSection');

const hudStatus = document.getElementById('hudStatus');
const exitCleanIndicator = document.getElementById('exitCleanIndicator');
const appContainer = document.querySelector('.app-container');
const renderAspectRatios = new Set(['ratio-9-16', 'ratio-16-9', 'ratio-1-1']);
const renderLayoutStyles = new Set(['layout-mobile', 'layout-desktop']);

// Sound Synthesis Function
function initAudio() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
}

function playKeySound(char) {
  if (!state.soundEnabled) return;
  initAudio();
  if (!audioCtx) return;

  const volume = state.soundVolume;
  const profile = state.soundProfile;

  // Master Gain
  const masterGain = audioCtx.createGain();
  masterGain.gain.setValueAtTime(volume * 0.15, audioCtx.currentTime); // keep it subtle
  masterGain.connect(audioCtx.destination);

  // Pitch variation (organic feel)
  const pitchFactor = 0.85 + Math.random() * 0.3; // 0.85 to 1.15

  // Generate Click sound depending on profile
  if (profile === 'mech-blue') {
    playMechClick(audioCtx, masterGain, 1600 * pitchFactor, 0.005, 0.002);
    setTimeout(() => {
      playMechClick(audioCtx, masterGain, 550 * pitchFactor, 0.015, 0.005);
    }, 15);
  } 
  else if (profile === 'mech-brown') {
    playMechClick(audioCtx, masterGain, 650 * pitchFactor, 0.012, 0.003);
  } 
  else if (profile === 'chiclet-laptop') {
    playChicletClick(audioCtx, masterGain, 900 * pitchFactor, 0.006);
  } 
  else if (profile === 'vintage-typewriter') {
    playTypewriterClack(audioCtx, masterGain, 400 * pitchFactor, 0.06);
  }
}

// Mech click helper
function playMechClick(ctx, dest, baseFreq, duration, noiseDuration) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  
  osc.type = 'triangle';
  osc.frequency.setValueAtTime(baseFreq, ctx.currentTime);
  osc.frequency.exponentialRampToValueAtTime(baseFreq * 0.1, ctx.currentTime + duration);

  gain.gain.setValueAtTime(1.0, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);

  // Noise generator for tactile feel
  const bufferSize = ctx.sampleRate * noiseDuration;
  const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) {
    data[i] = Math.random() * 2 - 1;
  }
  
  const noise = ctx.createBufferSource();
  noise.buffer = buffer;
  
  const noiseGain = ctx.createGain();
  noiseGain.gain.setValueAtTime(0.5, ctx.currentTime);
  noiseGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + noiseDuration);

  osc.connect(gain);
  gain.connect(dest);
  
  noise.connect(noiseGain);
  noiseGain.connect(dest);

  osc.start();
  osc.stop(ctx.currentTime + duration);
  
  noise.start();
  noise.stop(ctx.currentTime + noiseDuration);
}

// Chiclet laptop keypress click helper
function playChicletClick(ctx, dest, baseFreq, duration) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  
  osc.type = 'sine';
  osc.frequency.setValueAtTime(baseFreq, ctx.currentTime);
  osc.frequency.exponentialRampToValueAtTime(100, ctx.currentTime + duration);

  gain.gain.setValueAtTime(0.8, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);

  // Bandpass filtered noise
  const bufferSize = ctx.sampleRate * duration;
  const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) {
    data[i] = Math.random() * 2 - 1;
  }
  const noiseSource = ctx.createBufferSource();
  noiseSource.buffer = buffer;

  const filter = ctx.createBiquadFilter();
  filter.type = 'bandpass';
  filter.frequency.value = 4000;
  filter.Q.value = 2.0;

  const noiseGain = ctx.createGain();
  noiseGain.gain.setValueAtTime(0.4, ctx.currentTime);
  noiseGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);

  osc.connect(gain);
  gain.connect(dest);

  noiseSource.connect(filter);
  filter.connect(noiseGain);
  noiseGain.connect(dest);

  osc.start();
  osc.stop(ctx.currentTime + duration);
  noiseSource.start();
  noiseSource.stop(ctx.currentTime + duration);
}

// Vintage typewriter click
function playTypewriterClack(ctx, dest, baseFreq, duration) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  
  osc.type = 'sawtooth';
  osc.frequency.setValueAtTime(baseFreq, ctx.currentTime);
  osc.frequency.linearRampToValueAtTime(80, ctx.currentTime + duration);

  gain.gain.setValueAtTime(0.6, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);

  const filter = ctx.createBiquadFilter();
  filter.type = 'peaking';
  filter.frequency.value = 1500;
  filter.Q.value = 5.0;

  const bufferSize = ctx.sampleRate * duration * 1.5;
  const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) {
    data[i] = Math.random() * 2 - 1;
  }
  const noiseSource = ctx.createBufferSource();
  noiseSource.buffer = buffer;

  const noiseGain = ctx.createGain();
  noiseGain.gain.setValueAtTime(0.6, ctx.currentTime);
  noiseGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration * 0.6);

  osc.connect(filter);
  filter.connect(gain);
  gain.connect(dest);

  noiseSource.connect(noiseGain);
  noiseGain.connect(dest);

  osc.start();
  osc.stop(ctx.currentTime + duration);
  noiseSource.start();
  noiseSource.stop(ctx.currentTime + duration * 1.5);
}

function isRenderMode() {
  return new URLSearchParams(window.location.search).get('render') === '1';
}

function normalizeSubredditName(value) {
  const text = String(value || 'AskReddit').trim();
  if (!text) return 'r/AskReddit';
  return text.startsWith('r/') ? text : `r/${text.replace(/^\/?r\//, '')}`;
}

function syncDOMFromState() {
  subredditInput.value = state.subreddit;
  usernameInput.value = state.username;
  timeInput.value = state.time;
  postTitleInput.value = state.postTitle;
  postBodyInput.value = state.postBody;
  upvotesInput.value = state.upvotes;
  commentsCountInput.value = state.commentsCount;
  aspectRatioSelect.value = state.aspectRatio;
  layoutStyleSelect.value = state.layoutStyle;
  showTopbarCheckbox.checked = state.showTopbar;
  showLeftSidebarCheckbox.checked = state.showLeftSidebar;
  showRightSidebarCheckbox.checked = state.showRightSidebar;
  themeSelect.value = state.theme;
  bgSelect.value = state.background;
  safeZoneSelect.value = state.safeZone;
  typingSpeedRange.value = state.typingSpeed;
  typingJitterRange.value = state.jitter;
  punctuationDelayRange.value = state.punctuationDelay;
  mistakesCheckbox.checked = state.simulateMistakes;
  cursorBlinkCheckbox.checked = state.cursorBlink;
  soundToggleCheckbox.checked = state.soundEnabled;
  keyboardSoundSelect.value = state.soundProfile;
  soundVolumeRange.value = Math.round(state.soundVolume * 100);
}

function applyStoryData(story) {
  state.subreddit = normalizeSubredditName(story.subreddit);
  state.username = story.author || story.username || 'u/StoryTeller';
  state.time = story.time || '5h ago';
  state.postTitle = story.title || 'A Reddit story took a strange turn';
  state.postBody = story.body || '';
  state.upvotes = String(story.upvotes || story.score || '14.2k');
  state.commentsCount = String(story.comments_count || story.num_comments || '1.8k');
  state.comments = (story.comments || []).slice(0, 3).map((comment, index) => ({
    id: Number(comment.id || index + 1),
    username: comment.username || `u/Commenter_${index + 1}`,
    time: comment.time || '1h ago',
    body: comment.body || '',
    upvotes: String(comment.upvotes || '1')
  })).filter(comment => comment.body.trim());
  state.renderSlides = normalizeRenderSlides(story.slides);
}

function visibleNarrationTextForSlide(slide) {
  const parts = [];
  if (slide.title) parts.push(slide.title);
  if (slide.body) parts.push(slide.body);
  (slide.comments || []).forEach(comment => {
    if (comment.body) parts.push(comment.body);
  });
  return parts.join('\n\n').trim();
}

function countVisibleWords(text) {
  const matches = String(text || '').trim().match(/\S+/g);
  return matches ? matches.length : 0;
}

function normalizeRenderComment(comment, index) {
  return {
    id: Number(comment && comment.id) || index + 1,
    username: (comment && comment.username) || `u/Commenter_${index + 1}`,
    time: (comment && comment.time) || '1h ago',
    body: (comment && comment.body) || '',
    upvotes: String((comment && comment.upvotes) || '1')
  };
}

function fallbackRenderSlides() {
  const slides = [{
    id: 'story_1',
    type: 'story',
    title: state.postTitle || '',
    body: state.postBody || '',
    comments: []
  }];
  state.comments.forEach((comment, index) => {
    slides.push({
      id: `comment_${index + 1}`,
      type: 'comments',
      title: '',
      body: '',
      comments: [comment]
    });
  });
  return slides;
}

function normalizeRenderSlides(slides) {
  const source = Array.isArray(slides) && slides.length ? slides : fallbackRenderSlides();
  let cursor = 0;
  return source.map((slide, index) => {
    const normalized = {
      id: slide.id || `slide_${index + 1}`,
      type: slide.type || (slide.comments && slide.comments.length ? 'comments' : 'story'),
      title: String(slide.title || ''),
      body: String(slide.body || ''),
      comments: (slide.comments || []).map(normalizeRenderComment),
      wordStart: Number.isFinite(Number(slide.word_start)) ? Number(slide.word_start) : null,
      wordEnd: Number.isFinite(Number(slide.word_end)) ? Number(slide.word_end) : null,
      estimatedDuration: Math.max(1, Number(slide.estimated_duration_sec) || 3)
    };
    const wordCount = countVisibleWords(visibleNarrationTextForSlide(normalized));
    if (normalized.wordStart === null || normalized.wordEnd === null || normalized.wordEnd < normalized.wordStart) {
      normalized.wordStart = cursor;
      normalized.wordEnd = cursor + wordCount;
    }
    cursor = Math.max(cursor + wordCount, normalized.wordEnd);
    return normalized;
  });
}

function currentSlides() {
  if (!state.renderSlides || !state.renderSlides.length) {
    state.renderSlides = normalizeRenderSlides([]);
  }
  return state.renderSlides;
}

// ── Karaoke state ──────────────────────────────────────────────────────────
let karaokeWords   = [];  // [{word, start, end, el}, ...]
let karaokeAudio   = null;
let karaokeRafId   = null;
let karaokeReady   = false;
let karaokeActiveIndex = -1;
let karaokeActiveIndexes = [];
let karaokeRequired = false;
let activeRenderSlideIndex = -1;
const KARAOKE_GROUP_MIN_WORDS = 2;
const KARAOKE_GROUP_MAX_WORDS = 5;
const KARAOKE_GROUP_TARGET_CHARS = 24;
const KARAOKE_GROUP_MAX_CHARS = 34;

function syncKaraokeGlobals() {
  window.karaokeReady = karaokeReady;
  window.karaokeWords = karaokeWords;
}

function coerceKaraokeTime(value) {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function transcriptTokenText(value) {
  return value && (
    value.word ||
    value.text ||
    value.punctuated_word ||
    value.token ||
    value.value ||
    ''
  );
}

function transcriptTimeValue(value, keys) {
  for (const key of keys) {
    if (value[key] === undefined || value[key] === null) continue;
    const parsed = parseFloat(value[key]);
    if (!Number.isFinite(parsed)) continue;
    return key.toLowerCase().includes('ms') || parsed > 1000 ? parsed / 1000 : parsed;
  }
  return null;
}

function normalizeTranscriptWord(value) {
  const token = String(transcriptTokenText(value) || '').trim();
  if (!token) return null;

  const start = transcriptTimeValue(value, [
    'start', 'startTime', 'start_time', 'startMs', 'start_ms',
    'begin', 'beginTime', 'begin_time', 'beginMs', 'begin_ms',
    'offset', 'offsetMs', 'offset_ms'
  ]);
  let end = transcriptTimeValue(value, [
    'end', 'endTime', 'end_time', 'endMs', 'end_ms',
    'finish', 'finishTime', 'finish_time', 'stop', 'stopTime', 'stop_time'
  ]);
  if (end === null && start !== null) {
    const duration = transcriptTimeValue(value, ['duration', 'durationTime', 'duration_time', 'durationMs', 'duration_ms']);
    if (duration !== null) end = start + duration;
  }
  if (start === null || end === null || end < start) return null;

  return {
    word: token,
    start,
    end,
    el: null,
    timingSource: value.timing_source || value.timingSource || value.source || ''
  };
}

function isTranscriptWord(value) {
  return value && typeof value === 'object' &&
    normalizeTranscriptWord(value) !== null;
}

function collectTranscriptWords(value, found = []) {
  if (!value) return found;
  if (Array.isArray(value)) {
    value.forEach(item => collectTranscriptWords(item, found));
    return found;
  }
  if (typeof value !== 'object') return found;
  if (isTranscriptWord(value)) {
    found.push(value);
    return found;
  }
  Object.values(value).forEach(item => collectTranscriptWords(item, found));
  return found;
}

async function applyRenderModeFromQuery() {
  if (!isRenderMode()) return false;

  const params = new URLSearchParams(window.location.search);
  appContainer.classList.add('clean-mode', 'render-mode');
  document.body.classList.add('clean-mode', 'render-mode');
  exitCleanIndicator.style.opacity = '0';

  const karaokeRequested = params.get('karaoke') === '1';
  const transcriptPath = params.get('transcript') || (karaokeRequested ? 'narration.json' : null);
  const audioPath = params.get('audio') || (karaokeRequested ? 'narration.mp3' : null);
  karaokeRequired = karaokeRequested || params.has('transcript');
  window.karaokeRequired = karaokeRequired;
  const storyPath = params.get('story');
  if (storyPath) {
    const response = await fetch(storyPath, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`Could not load render story: ${storyPath}`);
    }
    applyStoryData(await response.json());
  }

  const requestedAspect = params.get('aspect') || params.get('aspectRatio') || 'ratio-9-16';
  const requestedLayout = params.get('layout') || params.get('layoutStyle');
  state.aspectRatio = renderAspectRatios.has(requestedAspect) ? requestedAspect : 'ratio-9-16';
  if (requestedLayout && renderLayoutStyles.has(requestedLayout)) {
    state.layoutStyle = requestedLayout;
  } else {
    state.layoutStyle = state.aspectRatio === 'ratio-16-9' ? 'layout-desktop' : 'layout-mobile';
  }
  state.theme        = params.get('theme')      || 'theme-reddit-midnight';
  state.background   = params.get('background') || 'bg-dark-aurora';
  state.safeZone     = 'sz-none';
  state.showTopbar   = false;
  state.showLeftSidebar  = false;
  state.showRightSidebar = false;
  state.soundEnabled     = false;
  state.simulateMistakes = false;
  state.cursorBlink      = true;
  state.typingSpeed      = 70;
  state.jitter           = 0;
  state.punctuationDelay = 0;
  state.cleanMode        = true;

  syncDOMFromState();

  // ── Try to load AI33 word-level transcript for karaoke mode ──────────────
  if (transcriptPath) {
    try {
      const tRes = await fetch(transcriptPath, { cache: 'no-store' });
      if (tRes.ok) {
        const transcript = await tRes.json();
        // Support flat arrays, {words: []}, segment wrappers, and nested AI33 task payloads.
        const words = collectTranscriptWords(transcript);
        if (words && words.length) {
          karaokeWords = words.map(normalizeTranscriptWord).filter(Boolean);
          if (karaokeWords.length) {
            karaokeReady = true;
            appContainer.classList.add('karaoke-mode');
            document.body.classList.add('karaoke-mode');
            syncKaraokeGlobals();
            if (audioPath) {
              karaokeAudio = new Audio(audioPath);
              karaokeAudio.preload = 'auto';
            }
          }
        }
      } else if (karaokeRequired) {
        throw new Error(`Karaoke transcript could not be loaded: ${transcriptPath}`);
      }
      if (karaokeRequired && !karaokeReady) {
        throw new Error(`Karaoke transcript had no usable word timings: ${transcriptPath}`);
      }
    } catch (error) {
      if (karaokeRequired) {
        throw error;
      }
      /* transcript optional — fall back to typing progress */
    }
  }

  return true;
}

function commentColor(comment, index) {
  const colors = ['#0079D3', '#FF4500', '#FFB000', '#00D474', '#D01416', '#7193FF', '#FF8717'];
  return colors[(Number(comment.id) || index + 1) % colors.length];
}

function createCommentCard(comment, index, bodyRenderer) {
  const avatarBg = commentColor(comment, index);
  const initial = comment.username.replace(/^u\//, '').charAt(0) || 'u';
  const card = document.createElement('div');
  card.className = 'comment-card';
  card.innerHTML = `
    <div class="comment-header">
      <div class="comment-avatar" style="background-color:${avatarBg}">${initial}</div>
      <span class="comment-author">${comment.username}</span>
      <span class="comment-time">${comment.time}</span>
    </div>
    <div class="comment-body" id="slide-comment-${comment.id}-${index}"></div>
    <div class="comment-footer">
      <div class="upvotes-action">
        <svg viewBox="0 0 24 24" class="icon"><path d="M12 4l-8 8h6v8h4v-8h6z"></path></svg>
        <span>${comment.upvotes}</span>
      </div>
      <span>Reply</span><span>Share</span>
    </div>`;
  postCommentsSection.appendChild(card);
  const bodyEl = document.getElementById(`slide-comment-${comment.id}-${index}`);
  bodyRenderer(comment.body || '', bodyEl);
}

function slideShowsPostFooter(slide) {
  return slide.type !== 'comments' || Boolean((slide.title || '').trim() || (slide.body || '').trim());
}

function renderSlideStatic(slide) {
  clearTimeout(typingTimeoutId);
  state.isPlaying = false;

  if (postFooter) {
    postFooter.style.display = slideShowsPostFooter(slide) ? 'flex' : 'none';
  }

  postTitleText.textContent = slide.title || '';
  postTitleContainer.style.display = slide.title ? 'block' : 'none';

  postBodyText.textContent = slide.body || '';
  postBodyWrapper.style.display = slide.body ? 'block' : 'none';

  postCommentsSection.innerHTML = '';
  (slide.comments || []).forEach((comment, index) => {
    createCommentCard(comment, index, (text, bodyEl) => {
      bodyEl.textContent = text;
    });
  });

  postTitleCursor.classList.remove('active', 'blink');
  postBodyCursor.classList.remove('active', 'blink');
  currentTextIndex = 0;
}

function slideIndexAtProgress(progress) {
  const slides = currentSlides();
  if (slides.length <= 1) return 0;
  const total = slides.reduce((sum, slide) => sum + Math.max(0.1, slide.estimatedDuration || 1), 0);
  const target = Math.max(0, Math.min(0.999999, Number(progress) || 0)) * total;
  let cursor = 0;
  for (let index = 0; index < slides.length; index++) {
    cursor += Math.max(0.1, slides[index].estimatedDuration || 1);
    if (target <= cursor) return index;
  }
  return slides.length - 1;
}

function renderSlideAtProgress(progress) {
  const slides = currentSlides();
  const index = slideIndexAtProgress(progress);
  renderSlideStatic(slides[index]);
  activeRenderSlideIndex = index;
  return true;
}

function renderTypingAtProgress(progress) {
  const safeProgress = Math.max(0, Math.min(1, Number(progress) || 0));
  if (isRenderMode() && currentSlides().length) {
    return renderSlideAtProgress(safeProgress);
  }
  clearTimeout(typingTimeoutId);
  state.isPlaying = false;

  const totalChars = typingQueue.reduce((sum, item) => sum + item.text.length, 0);
  let remainingChars = Math.floor(totalChars * safeProgress);
  let activeCursor = null;
  let activeIndex = safeProgress >= 1 ? typingQueue.length : 0;

  postTitleCursor.classList.remove('active');
  postBodyCursor.classList.remove('active');

  // Reset elements before applying progress state
  postTitleText.textContent = '';
  postBodyText.textContent = '';
  postBodyWrapper.style.display = 'none';
  postCommentsSection.innerHTML = '';

  typingQueue.forEach((item, index) => {
    const availableChars = Math.max(0, remainingChars);
    const visibleChars = Math.min(availableChars, item.text.length);
    const shouldMountItem = visibleChars > 0 || (safeProgress >= 1 && item.text.length === 0);

    if (shouldMountItem && item.setup) item.setup();
    if (item.element) {
      item.element.textContent = item.text.slice(0, visibleChars);
    }
    if (item.cursor) {
      item.cursor.classList.remove('active');
      if (shouldMountItem && visibleChars < item.text.length && !activeCursor) {
        activeCursor = item.cursor;
        activeIndex = index;
      }
    }
    remainingChars -= visibleChars;
  });

  if (!activeCursor && safeProgress < 1) {
    const firstTask = typingQueue.find(item => item.cursor);
    activeCursor = firstTask ? firstTask.cursor : null;
  }
  if (!activeCursor && typingQueue.length) {
    activeCursor = typingQueue[typingQueue.length - 1].cursor;
  }
  if (activeCursor) {
    activeCursor.classList.add('active');
    if (state.cursorBlink) activeCursor.classList.add('blink');
  }

  currentQueueIndex = activeIndex;
  currentTextIndex = 0;
  scrollCanvasToBottom();
}

function normalizeKaraokeToken(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase()
    .replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
}

const KARAOKE_LINK_PLACEHOLDER_RUNS = [
  ['ссылка', 'на', 'экране'],
  ['the', 'link', 'is', 'on', 'screen'],
  ['den', 'link', 'siehst', 'du', 'auf', 'dem', 'bildschirm'],
  ['el', 'enlace', 'está', 'en', 'pantalla'],
  ['o', 'link', 'está', 'na', 'tela'],
  ['le', 'lien', 'est', 'affiché', 'à', "l'écran"],
  ['il', 'link', 'è', 'sullo', 'schermo']
].map(phrase => phrase.map(normalizeKaraokeToken));

function isVisibleLinkToken(value) {
  const token = String(value || '').trim().replace(/[),.;:!?]+$/g, '');
  if (!token) return false;
  return /^(?:https?:\/\/|www\.)/i.test(token) ||
    /^[\p{L}\p{N}-]+(?:\.[\p{L}\p{N}-]+)+(?:[/?#]|$)/iu.test(token);
}

function matchLinkPlaceholderRun(expectedIndex, wordLimit) {
  for (const phrase of KARAOKE_LINK_PLACEHOLDER_RUNS) {
    if (expectedIndex + phrase.length > wordLimit) continue;
    let matches = true;
    for (let offset = 0; offset < phrase.length; offset++) {
      const word = karaokeWords[expectedIndex + offset];
      if (!word || word.el || normalizeKaraokeToken(word.word) !== phrase[offset]) {
        matches = false;
        break;
      }
    }
    if (matches) return phrase.length;
  }
  return 0;
}

function karaokePhraseBoundaryAfter(unit) {
  const token = String(unit?.token || '');
  const trailingSpace = String(unit?.spaceAfter || '');
  if (/\n/.test(trailingSpace)) return true;
  return /[.,;:!?…。！？،؛؟]+(?:["')\]}»”’]+)?$/u.test(token);
}

function karaokePhraseChars(units, start, end) {
  let text = '';
  for (let index = start; index < end; index++) {
    text += String(units[index]?.token || '');
    if (index < end - 1) {
      text += String(units[index]?.spaceAfter || ' ').replace(/\s+/g, ' ');
    }
  }
  return text.trim().length;
}

function splitTextForKaraoke(text) {
  const tokens = String(text || '').split(/(\s+)/).filter(token => token.length);
  const units = [];
  let leadingText = '';

  tokens.forEach(token => {
    if (/^\s+$/.test(token)) {
      if (units.length) {
        units[units.length - 1].spaceAfter += token;
      } else {
        leadingText += token;
      }
      return;
    }
    units.push({ token, spaceAfter: '' });
  });

  return { leadingText, units };
}

function planKaraokeGroups(units) {
  const groups = [];
  let index = 0;

  while (index < units.length) {
    if (isVisibleLinkToken(units[index].token)) {
      groups.push({ start: index, end: index + 1 });
      index += 1;
      continue;
    }

    let end = index + 1;
    while (end < units.length && end - index < KARAOKE_GROUP_MAX_WORDS) {
      if (karaokePhraseBoundaryAfter(units[end - 1]) || isVisibleLinkToken(units[end].token)) {
        break;
      }

      const nextChars = karaokePhraseChars(units, index, end + 1);
      const currentWords = end - index;
      if (currentWords >= KARAOKE_GROUP_MIN_WORDS && nextChars > KARAOKE_GROUP_MAX_CHARS) {
        break;
      }
      if (currentWords >= KARAOKE_GROUP_MIN_WORDS && karaokePhraseChars(units, index, end) >= KARAOKE_GROUP_TARGET_CHARS) {
        break;
      }
      if (nextChars > KARAOKE_GROUP_MAX_CHARS && currentWords >= 1) {
        break;
      }
      end += 1;
    }

    groups.push({ start: index, end });
    index = end;
  }

  return groups;
}

function slideIndexForWordIndex(wordIndex) {
  const slides = currentSlides();
  if (wordIndex < 0) return Math.max(0, activeRenderSlideIndex);
  for (let index = 0; index < slides.length; index++) {
    const slide = slides[index];
    if (wordIndex >= slide.wordStart && wordIndex < slide.wordEnd) {
      return index;
    }
  }
  return wordIndex >= (slides[slides.length - 1]?.wordEnd || 0) ? slides.length - 1 : 0;
}

function assignKaraokeWordToSpan(span, token, expectedIndex, wordLimit) {
  if (isVisibleLinkToken(token)) {
    const placeholderLength = matchLinkPlaceholderRun(expectedIndex, wordLimit);
    if (placeholderLength) {
      for (let offset = 0; offset < placeholderLength; offset++) {
        karaokeWords[expectedIndex + offset].el = span;
      }
      return expectedIndex + placeholderLength;
    }
  }

  const tokenNorm = normalizeKaraokeToken(token);
  const maxLookahead = Math.min(wordLimit, expectedIndex + 8);
  if (tokenNorm) {
    for (let index = expectedIndex; index < maxLookahead; index++) {
      if (!karaokeWords[index] || karaokeWords[index].el) continue;
      if (normalizeKaraokeToken(karaokeWords[index].word) === tokenNorm) {
        karaokeWords[index].el = span;
        return index + 1;
      }
    }
  }
  for (let index = expectedIndex; index < wordLimit; index++) {
    if (karaokeWords[index] && !karaokeWords[index].el) {
      karaokeWords[index].el = span;
      return index + 1;
    }
  }
  return expectedIndex;
}

// ── Karaoke DOM builder ────────────────────────────────────────────────────
// Renders exactly one slide and attaches transcript words only to visible text.
function buildKaraokeDOM(slideIndex = activeRenderSlideIndex >= 0 ? activeRenderSlideIndex : 0) {
  const slides = currentSlides();
  const slide = slides[Math.max(0, Math.min(slides.length - 1, slideIndex))];
  karaokeWords.forEach(word => { word.el = null; });
  karaokeActiveIndex = -1;
  karaokeActiveIndexes = [];

  if (postFooter) {
    postFooter.style.display = slideShowsPostFooter(slide) ? 'flex' : 'none';
  }

  postTitleText.innerHTML = '';
  postTitleContainer.style.display = 'none';
  postBodyWrapper.style.display = 'none';
  postCommentsSection.innerHTML = '';

  let wordIdx = Math.max(0, Number(slide.wordStart) || 0);
  const wordLimit = Math.min(karaokeWords.length, Math.max(wordIdx, Number(slide.wordEnd) || karaokeWords.length));

  function wrapWordsIntoEl(text, container) {
    container.innerHTML = '';
    const { leadingText, units } = splitTextForKaraoke(text);
    if (leadingText) {
      container.appendChild(document.createTextNode(leadingText));
    }

    planKaraokeGroups(units).forEach(group => {
      const groupSpan = document.createElement('span');
      groupSpan.className = 'kw kw-group';
      container.appendChild(groupSpan);

      for (let index = group.start; index < group.end; index++) {
        const unit = units[index];
        groupSpan.appendChild(document.createTextNode(unit.token));
        wordIdx = assignKaraokeWordToSpan(groupSpan, unit.token, wordIdx, wordLimit);
        if (index < group.end - 1) {
          groupSpan.appendChild(document.createTextNode(unit.spaceAfter || ' '));
        }
      }
      if (units[group.end - 1]?.spaceAfter) {
        container.appendChild(document.createTextNode(units[group.end - 1].spaceAfter));
      }
    });
  }

  if ((slide.title || '').trim()) {
    postTitleContainer.style.display = 'block';
    wrapWordsIntoEl(slide.title, postTitleText);
  }

  if ((slide.body || '').trim()) {
    postBodyWrapper.style.display = 'block';
    wrapWordsIntoEl(slide.body, postBodyText);
  }

  (slide.comments || []).forEach((comment, index) => {
    if (!comment.body.trim()) return;
    createCommentCard(comment, index, wrapWordsIntoEl);
  });

  activeRenderSlideIndex = slideIndex;
}

function findKaraokeWordIndex(timeSeconds) {
  let active = -1;
  for (let i = 0; i < karaokeWords.length; i++) {
    const word = karaokeWords[i];
    if (timeSeconds >= word.start && timeSeconds <= word.end) return i;
    if (timeSeconds > word.end && (i === karaokeWords.length - 1 || timeSeconds < karaokeWords[i + 1].start)) {
      active = i;
    }
  }
  return active;
}

function karaokeGroupIndexes(active) {
  if (active < 0 || !karaokeWords[active]) return [];
  const activeEl = karaokeWords[active].el;
  if (!activeEl) return [];
  const slides = currentSlides();
  const slideIndex = slideIndexForWordIndex(active);
  const slide = slides[Math.max(0, Math.min(slides.length - 1, slideIndex))] || {};
  const slideStart = Math.max(0, Number(slide.wordStart) || 0);
  const slideEnd = Math.min(
    karaokeWords.length,
    Math.max(slideStart + 1, Number(slide.wordEnd) || karaokeWords.length)
  );
  const indexes = [];
  for (let index = slideStart; index < slideEnd; index++) {
    if (karaokeWords[index] && karaokeWords[index].el === activeEl) {
      indexes.push(index);
    }
  }
  return indexes;
}

function setKaraokeActiveIndex(active) {
  const nextIndexes = karaokeGroupIndexes(active);
  if (
    active === karaokeActiveIndex &&
    nextIndexes.length === karaokeActiveIndexes.length &&
    nextIndexes.every((index, offset) => index === karaokeActiveIndexes[offset])
  ) {
    return;
  }
  karaokeActiveIndexes.forEach(index => {
    if (karaokeWords[index] && karaokeWords[index].el) {
      karaokeWords[index].el.classList.remove('kw-active');
    }
  });
  nextIndexes.forEach(index => {
    if (karaokeWords[index] && karaokeWords[index].el) {
      karaokeWords[index].el.classList.add('kw-active');
    }
  });
  karaokeActiveIndex = active;
  karaokeActiveIndexes = nextIndexes;
}

function renderKaraokeAtTime(timeSeconds) {
  if (!karaokeReady) return false;
  const active = findKaraokeWordIndex(coerceKaraokeTime(timeSeconds));
  const slideIndex = slideIndexForWordIndex(active);
  if (activeRenderSlideIndex !== slideIndex || !karaokeWords.some(word => word.el)) {
    buildKaraokeDOM(slideIndex);
  }
  setKaraokeActiveIndex(active);
  return true;
}

window.renderKaraokeAtTime = renderKaraokeAtTime;
window.karaokeReady = false;
window.karaokeWords = karaokeWords;

// ── Karaoke RAF playback loop ──────────────────────────────────────────────
function startKaraokePlayback() {
  if (!karaokeReady || !karaokeAudio) return;

  renderKaraokeAtTime(0);

  function tick() {
    const t = karaokeAudio.currentTime;
    renderKaraokeAtTime(t);

    if (!karaokeAudio.ended) {
      karaokeRafId = requestAnimationFrame(tick);
    } else {
      // Hold last word highlighted for 1 sec then clear
      setTimeout(() => {
        setKaraokeActiveIndex(-1);
        document.body.dataset.renderReady = 'done';
      }, 1000);
    }
  }

  karaokeAudio.play().then(() => {
    karaokeRafId = requestAnimationFrame(tick);
    document.body.dataset.renderReady = 'karaoke';
  }).catch(err => {
    console.warn('Karaoke audio play failed, falling back to typing:', err);
    karaokeReady = false;
    syncKaraokeGlobals();
    renderTypingAtProgress(new URLSearchParams(window.location.search).get('progress') || 0);
    document.body.dataset.renderReady = 'true';
  });
}

// Initialise settings on page load
async function init() {
  // Sync checkbox UI elements with initial state defaults on page load
  showTopbarCheckbox.checked = state.showTopbar;
  showLeftSidebarCheckbox.checked = state.showLeftSidebar;
  showRightSidebarCheckbox.checked = state.showRightSidebar;

  loadStateFromDOM();
  const renderMode = await applyRenderModeFromQuery();
  renderCommentsEditor();
  applyStyles();
  resetTyping();
  setupEventListeners();

  if (renderMode) {
    if (karaokeReady) {
      // Deterministic renderer path: render.py advances the highlight per frame.
      // Do not start browser audio playback here; autoplay failures must not
      // disable karaoke during headless capture.
      buildKaraokeDOM();
      renderKaraokeAtTime(coerceKaraokeTime(new URLSearchParams(window.location.search).get('time') || 0));
      document.body.dataset.renderReady = 'karaoke';
    } else {
      if (karaokeRequired) {
        throw new Error('Karaoke render was required, but transcript/audio did not initialize.');
      }
      // Fallback: deterministic slide progress for renders without usable word timings.
      renderTypingAtProgress(new URLSearchParams(window.location.search).get('progress') || 0);
      document.body.dataset.renderReady = 'true';
    }
  }
}

// Load state from controls
function loadStateFromDOM() {
  state.subreddit = subredditInput.value;
  state.username = usernameInput.value;
  state.time = timeInput.value;
  state.postTitle = postTitleInput.value;
  state.postBody = postBodyInput.value;
  state.upvotes = upvotesInput.value;
  state.commentsCount = commentsCountInput.value;

  state.aspectRatio = aspectRatioSelect.value;
  state.layoutStyle = layoutStyleSelect.value;
  state.showTopbar = showTopbarCheckbox.checked;
  state.showLeftSidebar = showLeftSidebarCheckbox.checked;
  state.showRightSidebar = showRightSidebarCheckbox.checked;
  state.theme = themeSelect.value;
  state.background = bgSelect.value;
  state.safeZone = safeZoneSelect.value;

  state.typingSpeed = parseInt(typingSpeedRange.value);
  state.jitter = parseInt(typingJitterRange.value);
  state.punctuationDelay = parseInt(punctuationDelayRange.value);
  state.simulateMistakes = mistakesCheckbox.checked;
  state.cursorBlink = cursorBlinkCheckbox.checked;

  state.soundEnabled = soundToggleCheckbox.checked;
  state.soundProfile = keyboardSoundSelect.value;
  state.soundVolume = parseFloat(soundVolumeRange.value) / 100;
  
  typingSpeedVal.textContent = `${state.typingSpeed} CPS`;
  typingJitterVal.textContent = `${state.jitter}%`;
  punctuationDelayVal.textContent = `${state.punctuationDelay}ms`;
  soundVolumeVal.textContent = `${Math.round(state.soundVolume * 100)}%`;
}

// Render dynamic list of comments in sidebar
function renderCommentsEditor() {
  commentsListContainer.innerHTML = '';
  state.comments.forEach((comment, index) => {
    const item = document.createElement('div');
    item.className = 'comment-editor-item';
    item.innerHTML = `
      <div class="comment-editor-header">
        <span class="comment-editor-index">Comment #${index + 1}</span>
        <button class="comment-delete-btn" data-id="${comment.id}">Delete</button>
      </div>
      <div class="input-row" style="margin-bottom: 8px;">
        <div class="input-group" style="margin-bottom: 0;">
          <label>Username</label>
          <input type="text" class="comment-username-input" data-id="${comment.id}" value="${comment.username}">
        </div>
        <div class="input-group" style="margin-bottom: 0;">
          <label>Time</label>
          <input type="text" class="comment-time-input" data-id="${comment.id}" value="${comment.time}">
        </div>
      </div>
      <div class="input-group" style="margin-bottom: 8px;">
        <label>Body Text</label>
        <textarea class="comment-body-input" data-id="${comment.id}" rows="2">${comment.body}</textarea>
      </div>
      <div class="input-group" style="margin-bottom: 0;">
        <label>Upvotes</label>
        <input type="text" class="comment-votes-input" data-id="${comment.id}" value="${comment.upvotes}">
      </div>
    `;
    commentsListContainer.appendChild(item);
  });
}

// Apply visual styles to simulator
function applyStyles() {
  postSubreddit.textContent = state.subreddit;
  postAuthorName.textContent = state.username;
  postTime.textContent = state.time;
  postVotes.textContent = state.upvotes;
  postCommentsCount.textContent = state.commentsCount;
  
  const firstLetter = state.subreddit.replace(/^r\//, '').charAt(0) || 'r';
  postAvatar.textContent = firstLetter;
  postAvatar.style.backgroundColor = state.avatarColor;

  // Move the Reddit Card DOM node between Mobile/Desktop wrapper sections
  if (state.layoutStyle === 'layout-desktop') {
    if (redditCard.parentElement !== desktopCenterFeed) {
      desktopCenterFeed.appendChild(redditCard);
    }
    
    document.getElementById('desktopLeftSubName').textContent = state.subreddit;
    document.getElementById('desktopRightSubName').textContent = state.subreddit;
    
    const leftIcon = document.getElementById('desktopLeftSubIcon');
    leftIcon.textContent = firstLetter;
    leftIcon.style.backgroundColor = state.avatarColor;
    
    canvasContainer.className = `canvas-container ${state.aspectRatio} ${state.background} layout-desktop`;
    
    // Toggle Desktop visibility classes
    if (state.showTopbar) {
      desktopLayoutWrapper.classList.remove('hide-nav');
    } else {
      desktopLayoutWrapper.classList.add('hide-nav');
    }
    if (state.showLeftSidebar) {
      desktopLayoutWrapper.classList.remove('hide-left');
    } else {
      desktopLayoutWrapper.classList.add('hide-left');
    }
    if (state.showRightSidebar) {
      desktopLayoutWrapper.classList.remove('hide-right');
    } else {
      desktopLayoutWrapper.classList.add('hide-right');
    }
    
    document.getElementById('desktopTogglesWrapper').style.display = 'block';
  } else {
    if (redditCard.parentElement !== canvasContainer) {
      canvasContainer.insertBefore(redditCard, document.getElementById('safeZoneOverlay'));
    }
    canvasContainer.className = `canvas-container ${state.aspectRatio} ${state.background} layout-mobile`;
    document.getElementById('desktopTogglesWrapper').style.display = 'none';
  }

  // Handle Safe zone overlays
  canvasContainer.classList.remove('show-sz-shorts', 'show-sz-reels', 'show-sz-tiktok');
  if (state.safeZone !== 'sz-none') {
    canvasContainer.classList.add(`show-${state.safeZone}`);
  }

  // Theme styling applying (using classList to avoid overwriting toggle classes)
  redditCard.classList.remove('theme-reddit-midnight', 'theme-reddit-dark', 'theme-reddit-light');
  redditCard.classList.add(state.theme);
  
  const deskWrapper = document.getElementById('desktopLayoutWrapper');
  deskWrapper.classList.remove('theme-reddit-midnight', 'theme-reddit-dark', 'theme-reddit-light');
  deskWrapper.classList.add(state.theme);

  // Cursors blinking settings
  const cursors = document.querySelectorAll('.cursor');
  cursors.forEach(c => {
    if (state.cursorBlink) {
      c.classList.add('blink');
    } else {
      c.classList.remove('blink');
    }
  });
}

// Reset typing simulation state
function resetTyping() {
  clearTimeout(typingTimeoutId);
  state.isPlaying = false;
  playPauseBtn.textContent = 'Play Animation';
  playPauseBtn.className = 'btn btn-success';
  hudStatus.textContent = 'Ready';
  hudStatus.style.color = '#10b981';

  if (isRenderMode()) {
    postTitleText.textContent = '';
    postBodyText.textContent = '';
    postBodyWrapper.style.display = 'none';
    postCommentsSection.innerHTML = '';
  } else {
    postTitleText.textContent = state.postTitle;
    if (state.postBody.trim()) {
      postBodyText.textContent = state.postBody;
      postBodyWrapper.style.display = 'block';
    } else {
      postBodyText.textContent = '';
      postBodyWrapper.style.display = 'none';
    }
    
    // Render comments fully for local preview
    postCommentsSection.innerHTML = '';
    state.comments.forEach(comment => {
      const card = document.createElement('div');
      card.className = 'comment-card';
      const colors = ['#0079D3', '#FF4500', '#FFB000', '#00D474', '#D01416', '#7193FF', '#FF8717'];
      const avatarBg = colors[comment.id % colors.length];
      const commentFirstLetter = comment.username.replace(/^u\//, '').charAt(0) || 'u';
      card.innerHTML = `
        <div class="comment-header">
          <div class="comment-avatar" style="background-color: ${avatarBg}">${commentFirstLetter}</div>
          <span class="comment-author">${comment.username}</span>
          <span class="comment-time">${comment.time}</span>
        </div>
        <div class="comment-body">
          <span>${comment.body}</span>
        </div>
        <div class="comment-footer">
          <div class="upvotes-action">
            <svg viewBox="0 0 24 24" class="icon"><path d="M12 4l-8 8h6v8h4v-8h6z"></path></svg>
            <span>${comment.upvotes}</span>
          </div>
          <span>Reply</span>
          <span>Share</span>
        </div>
      `;
      postCommentsSection.appendChild(card);
    });
  }

  postTitleCursor.classList.add('active');
  postBodyCursor.classList.remove('active');

  typingQueue = [];
  
  if (state.postTitle.trim()) {
    typingQueue.push({
      type: 'title',
      text: state.postTitle,
      element: postTitleText,
      cursor: postTitleCursor
    });
  }

  if (state.postBody.trim()) {
    typingQueue.push({
      type: 'body',
      text: state.postBody,
      element: postBodyText,
      cursor: postBodyCursor,
      setup: () => {
        postBodyWrapper.style.display = 'block';
        postTitleCursor.classList.remove('active');
        postBodyCursor.classList.add('active');
        scrollCanvasToBottom();
      }
    });
  }

  state.comments.forEach((comment, index) => {
    const commentTask = {
      type: 'comment',
      text: comment.body,
      setup: () => {
        if (index === 0) {
          postBodyCursor.classList.remove('active');
          postTitleCursor.classList.remove('active');
        } else {
          const prevCommentCursor = document.getElementById(`commentCursor-${state.comments[index - 1].id}`);
          if (prevCommentCursor) prevCommentCursor.classList.remove('active');
        }

        const commentCard = document.createElement('div');
        commentCard.className = 'comment-card';
        const colors = ['#0079D3', '#FF4500', '#FFB000', '#00D474', '#D01416', '#7193FF', '#FF8717'];
        const avatarBg = colors[comment.id % colors.length];
        const commentFirstLetter = comment.username.replace(/^u\//, '').charAt(0) || 'u';

        commentCard.innerHTML = `
          <div class="comment-header">
            <div class="comment-avatar" style="background-color: ${avatarBg}">${commentFirstLetter}</div>
            <span class="comment-author">${comment.username}</span>
            <span class="comment-time">${comment.time}</span>
          </div>
          <div class="comment-body">
            <span class="typed-text" id="commentText-${comment.id}"></span><span class="cursor active" id="commentCursor-${comment.id}"></span>
          </div>
          <div class="comment-footer">
            <div class="upvotes-action">
              <svg viewBox="0 0 24 24" class="icon"><path d="M12 4l-8 8h6v8h4v-8h6z"></path></svg>
              <span>${comment.upvotes}</span>
            </div>
            <span>Reply</span>
            <span>Share</span>
          </div>
        `;
        postCommentsSection.appendChild(commentCard);
        scrollCanvasToBottom();

        commentTask.element = document.getElementById(`commentText-${comment.id}`);
        commentTask.cursor = document.getElementById(`commentCursor-${comment.id}`);
        if (state.cursorBlink && commentTask.cursor) {
          commentTask.cursor.classList.add('blink');
        }
      }
    };
    typingQueue.push(commentTask);
  });

  currentQueueIndex = 0;
  currentTextIndex = 0;
  isErrorTyping = false;
}

// Start typing sequence loop
function startTyping() {
  if (typingQueue.length === 0) return;
  
  if (currentQueueIndex === 0 && currentTextIndex === 0) {
    postTitleText.textContent = '';
    postBodyText.textContent = '';
    postBodyWrapper.style.display = 'none';
    postCommentsSection.innerHTML = '';
    postTitleCursor.classList.add('active');
    postBodyCursor.classList.remove('active');
  }
  
  state.isPlaying = true;
  playPauseBtn.textContent = 'Pause Animation';
  playPauseBtn.className = 'btn btn-primary';
  hudStatus.textContent = 'Typing...';
  hudStatus.style.color = '#ff9900';

  typeNextChar();
}

// Pause typing loop
function pauseTyping() {
  state.isPlaying = false;
  clearTimeout(typingTimeoutId);
  playPauseBtn.textContent = 'Play Animation';
  playPauseBtn.className = 'btn btn-success';
  hudStatus.textContent = 'Paused';
  hudStatus.style.color = '#38bdf8';
}

// The core Typing Logic engine
function typeNextChar() {
  if (!state.isPlaying) return;

  if (currentQueueIndex >= typingQueue.length) {
    finishTyping();
    return;
  }

  const currentTask = typingQueue[currentQueueIndex];

  if (currentTextIndex === 0 && currentTask.setup) {
    currentTask.setup();
  }

  const fullText = currentTask.text;

  if (currentTask.cursor) {
    currentTask.cursor.classList.remove('blink');
    currentTask.cursor.classList.add('active');
  }

  const baseSpeedDelay = 1000 / state.typingSpeed;
  const jitterRange = (state.jitter / 100) * baseSpeedDelay;
  let delay = baseSpeedDelay + (Math.random() * jitterRange * 2 - jitterRange);

  // Mistakes/Typos logic
  if (state.simulateMistakes && !isErrorTyping && Math.random() < 0.015 && currentTextIndex > 3 && currentTextIndex < fullText.length - 3) {
    isErrorTyping = true;
    const incorrectChar = getRandomAdjacentChar(fullText.charAt(currentTextIndex));
    currentTask.element.textContent += incorrectChar;
    playKeySound(incorrectChar);
    
    setTimeout(() => {
      currentTask.element.textContent = currentTask.element.textContent.slice(0, -1);
      playKeySound('Backspace');
      
      setTimeout(() => {
        isErrorTyping = false;
        typeNextChar();
      }, baseSpeedDelay * 2.5);
      
    }, baseSpeedDelay * 3);
    
    return;
  }

  const char = fullText.charAt(currentTextIndex);
  currentTask.element.textContent += char;
  playKeySound(char);
  currentTextIndex++;

  if (['.', '?', '!'].includes(char)) {
    delay += state.punctuationDelay;
  } else if ([',', ';', '-', ':'].includes(char)) {
    delay += state.punctuationDelay * 0.5;
  }

  scrollCanvasToBottom();

  if (currentTextIndex >= fullText.length) {
    currentQueueIndex++;
    currentTextIndex = 0;
    
    if (currentTask.cursor) {
      if (state.cursorBlink) currentTask.cursor.classList.add('blink');
    }
    
    typingTimeoutId = setTimeout(typeNextChar, 1000);
  } else {
    typingTimeoutId = setTimeout(typeNextChar, delay);
  }
}

// Typing process finished
function finishTyping() {
  state.isPlaying = false;
  playPauseBtn.textContent = 'Replay Animation';
  playPauseBtn.className = 'btn btn-success';
  hudStatus.textContent = 'Completed';
  hudStatus.style.color = '#10b981';
  
  const lastTask = typingQueue[typingQueue.length - 1];
  if (lastTask && lastTask.cursor) {
    lastTask.cursor.classList.add('active');
    if (state.cursorBlink) lastTask.cursor.classList.add('blink');
  }
}

// Scrolling helper to ensure typing cursors stay visible in video frame
function scrollCanvasToBottom() {
  if (state.layoutStyle === 'layout-desktop') {
    desktopCenterFeed.scrollTop = desktopCenterFeed.scrollHeight;
  } else {
    canvasContainer.scrollTop = canvasContainer.scrollHeight;
  }
}

// Generate adjacent keys for realistic typos
function getRandomAdjacentChar(char) {
  const adjacentKeys = {
    'a': 'qwsz', 'b': 'vghn', 'c': 'xdfv', 'd': 'ersfxc', 'e': 'wsdr',
    'f': 'rtgvcd', 'g': 'tyhbvf', 'h': 'yujnbg', 'i': 'ujko', 'j': 'uikmnh',
    'k': 'ijlm', 'l': 'opk', 'm': 'njk', 'n': 'bhjm', 'o': 'iklp',
    'p': 'ol', 'q': 'wa', 'r': 'edtf', 's': 'wedxza', 't': 'rfgy',
    'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc', 'y': 'tghu',
    'z': 'asx', ' ': 'c vbnm'
  };
  
  const lowers = char.toLowerCase();
  if (adjacentKeys[lowers]) {
    const list = adjacentKeys[lowers];
    const picked = list.charAt(Math.floor(Math.random() * list.length));
    return char === char.toUpperCase() ? picked.toUpperCase() : picked;
  }
  return 'e';
}

// Set up UI listeners
function setupEventListeners() {
  
  // Tabs Navigation
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
    });
  });

  const inputHandler = (element, stateKey, needsStyle = false) => {
    element.addEventListener('input', (e) => {
      state[stateKey] = e.target.value;
      if (needsStyle) applyStyles();
      resetTyping();
    });
  };

  inputHandler(subredditInput, 'subreddit', true);
  inputHandler(usernameInput, 'username', true);
  inputHandler(timeInput, 'time', true);
  inputHandler(postTitleInput, 'postTitle');
  inputHandler(postBodyInput, 'postBody');
  inputHandler(upvotesInput, 'upvotes', true);
  inputHandler(commentsCountInput, 'commentsCount', true);

  // Avatar colors
  document.querySelectorAll('.color-dot').forEach(dot => {
    dot.addEventListener('click', (e) => {
      document.querySelectorAll('.color-dot').forEach(d => d.classList.remove('active'));
      dot.classList.add('active');
      state.avatarColor = dot.dataset.color;
      applyStyles();
    });
  });

  // Comments event handling
  addCommentBtn.addEventListener('click', () => {
    const nextId = state.comments.length > 0 ? Math.max(...state.comments.map(c => c.id)) + 1 : 1;
    state.comments.push({
      id: nextId,
      username: `u/User_${nextId}`,
      time: '1h ago',
      body: 'Add your reply text here...',
      upvotes: '1'
    });
    renderCommentsEditor();
    bindCommentsInputs();
    resetTyping();
  });

  function bindCommentsInputs() {
    document.querySelectorAll('.comment-username-input').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.target.dataset.id);
        const comment = state.comments.find(c => c.id === id);
        if (comment) comment.username = e.target.value;
        resetTyping();
      });
    });

    document.querySelectorAll('.comment-time-input').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.target.dataset.id);
        const comment = state.comments.find(c => c.id === id);
        if (comment) comment.time = e.target.value;
        resetTyping();
      });
    });

    document.querySelectorAll('.comment-body-input').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.target.dataset.id);
        const comment = state.comments.find(c => c.id === id);
        if (comment) comment.body = e.target.value;
        resetTyping();
      });
    });

    document.querySelectorAll('.comment-votes-input').forEach(input => {
      input.addEventListener('input', (e) => {
        const id = parseInt(e.target.dataset.id);
        const comment = state.comments.find(c => c.id === id);
        if (comment) comment.upvotes = e.target.value;
        resetTyping();
      });
    });

    document.querySelectorAll('.comment-delete-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const id = parseInt(e.target.dataset.id);
        state.comments = state.comments.filter(c => c.id !== id);
        renderCommentsEditor();
        bindCommentsInputs();
        resetTyping();
      });
    });
  }
  bindCommentsInputs();

  // Layout Dropdowns
  aspectRatioSelect.addEventListener('change', (e) => {
    state.aspectRatio = e.target.value;
    applyStyles();
  });
  layoutStyleSelect.addEventListener('change', (e) => {
    state.layoutStyle = e.target.value;
    applyStyles();
  });
  showTopbarCheckbox.addEventListener('change', (e) => {
    state.showTopbar = e.target.checked;
    applyStyles();
  });
  showLeftSidebarCheckbox.addEventListener('change', (e) => {
    state.showLeftSidebar = e.target.checked;
    applyStyles();
  });
  showRightSidebarCheckbox.addEventListener('change', (e) => {
    state.showRightSidebar = e.target.checked;
    applyStyles();
  });
  themeSelect.addEventListener('change', (e) => {
    state.theme = e.target.value;
    applyStyles();
  });
  bgSelect.addEventListener('change', (e) => {
    state.background = e.target.value;
    applyStyles();
  });
  safeZoneSelect.addEventListener('change', (e) => {
    state.safeZone = e.target.value;
    applyStyles();
  });

  // Typing sliders
  typingSpeedRange.addEventListener('input', (e) => {
    state.typingSpeed = parseInt(e.target.value);
    typingSpeedVal.textContent = `${state.typingSpeed} CPS`;
  });
  typingJitterRange.addEventListener('input', (e) => {
    state.jitter = parseInt(e.target.value);
    typingJitterVal.textContent = `${state.jitter}%`;
  });
  punctuationDelayRange.addEventListener('input', (e) => {
    state.punctuationDelay = parseInt(e.target.value);
    punctuationDelayVal.textContent = `${state.punctuationDelay}ms`;
  });
  mistakesCheckbox.addEventListener('change', (e) => {
    state.simulateMistakes = e.target.checked;
  });
  cursorBlinkCheckbox.addEventListener('change', (e) => {
    state.cursorBlink = e.target.checked;
    applyStyles();
  });

  // Sound Config
  soundToggleCheckbox.addEventListener('change', (e) => {
    state.soundEnabled = e.target.checked;
  });
  keyboardSoundSelect.addEventListener('change', (e) => {
    state.soundProfile = e.target.value;
  });
  soundVolumeRange.addEventListener('input', (e) => {
    state.soundVolume = parseFloat(e.target.value) / 100;
    soundVolumeVal.textContent = `${e.target.value}%`;
  });

  // Playback Control Buttons
  playPauseBtn.addEventListener('click', () => {
    if (state.isPlaying) {
      pauseTyping();
    } else {
      if (currentQueueIndex >= typingQueue.length) {
        resetTyping();
      }
      startTyping();
    }
  });

  resetBtn.addEventListener('click', () => {
    resetTyping();
  });

  cleanModeBtn.addEventListener('click', () => {
    enterCleanMode();
  });

  // Keyboard Shortcuts
  document.addEventListener('keydown', (e) => {
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      return;
    }

    if (e.code === 'Space') {
      e.preventDefault();
      playPauseBtn.click();
    } 
    else if (e.code === 'KeyR') {
      resetBtn.click();
    } 
    else if (e.code === 'Escape' && state.cleanMode) {
      exitCleanMode();
    }
  });
}

function enterCleanMode() {
  state.cleanMode = true;
  appContainer.classList.add('clean-mode');
  exitCleanIndicator.style.opacity = '1';
  
  if (!state.isPlaying) {
    resetTyping();
    setTimeout(startTyping, 1000);
  }
}

function exitCleanMode() {
  state.cleanMode = false;
  appContainer.classList.remove('clean-mode');
  exitCleanIndicator.style.opacity = '0';
  pauseTyping();
}

window.addEventListener('DOMContentLoaded', () => {
  init().catch((error) => {
    console.error(error);
    document.body.dataset.renderError = error.message || String(error);
  });
});
