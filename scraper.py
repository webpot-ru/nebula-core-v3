import json
import random
import sys
import os
import re
import hashlib
from datetime import datetime, timezone

# ─────────────────────────────────────────────
#  PRAW-based Reddit scraper with virality scoring
#  Requires env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
#                     REDDIT_USERNAME, REDDIT_PASSWORD
# ─────────────────────────────────────────────

def get_reddit():
    """Authenticate with Reddit via PRAW (script app or read-only public access)."""
    try:
        import praw
    except ImportError:
        os.system("pip3 install praw -q")
        import praw

    client_id = os.environ.get("REDDIT_CLIENT_ID", "JYA8zMAO2b1GTIZnHoITbg")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "kKDnjQmqAidycdvliILdPvoMq15w_A")
    username = os.environ.get("REDDIT_USERNAME", "Complex_Lack4476")
    password = os.environ.get("REDDIT_PASSWORD", "")

    if not password:
        # Read-only mode for public data (does not require username/password)
        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="macos:ChonkerTalksBot:v1.0 (read-only)"
        )
    else:
        # Authenticated script mode
        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=f"macos:ChonkerTalksBot:v1.0 (by /u/{username})"
        )


def format_count(n):
    """Format a number as '12.3k' or '999'."""
    if n >= 1000:
        return f"{round(n / 1000, 1)}k"
    return str(n)


def virality_score(post):
    """
    Score a Reddit post's viral potential on a 0–100 scale.

    Signals:
      - High comment/upvote ratio  → controversy (people argue → YT comments boost)
      - High upvote count          → proven mainstream appeal
      - High comment count         → engagement
      - Long body text             → enough content for a full narration video
    """
    score = 0
    ups = max(post.score, 1)
    ratio = post.num_comments / ups

    if ratio > 0.1:                  score += 30  # Very controversial
    elif ratio > 0.05:               score += 15  # Moderately controversial

    if post.score > 15_000:          score += 20  # Mega-viral bonus
    if post.score > 5_000:           score += 25  # Popular
    elif post.score > 1_000:         score += 10  # Decent

    if post.num_comments > 1_000:    score += 15  # High engagement
    elif post.num_comments > 300:    score += 7

    body_len = len(post.selftext or "")
    if body_len > 1_000:             score += 10  # Long story = good video
    elif body_len > 300:             score += 5

    return min(score, 100)


AI_QUALITY_ENABLED = os.environ.get("AI_QUALITY_CHECK", "1") != "0"
AI_QUALITY_FAIL_OPEN = os.environ.get("AI_QUALITY_FAIL_OPEN", "0") == "1"
DEFAULT_MAX_AI_CANDIDATES = int(os.environ.get("MAX_AI_CANDIDATES", "12"))
DEFAULT_CANDIDATE_LIMIT = int(os.environ.get("CANDIDATE_LIMIT_PER_SOURCE", "25"))
DEFAULT_MAX_SUBREDDITS_PER_TOPIC = int(os.environ.get("MAX_SUBREDDITS_PER_TOPIC", "4"))
DEFAULT_MAX_TIME_WINDOWS_PER_TOPIC = int(os.environ.get("MAX_TIME_WINDOWS_PER_TOPIC", "2"))
DEFAULT_SIMILARITY_THRESHOLD = float(os.environ.get("STORY_SIMILARITY_THRESHOLD", "0.72"))
DEFAULT_TOPIC_FATIGUE_LOOKBACK = int(os.environ.get("TOPIC_FATIGUE_LOOKBACK", "10"))
VALID_TIME_FILTERS = ("day", "week", "month", "year")


TOPIC_FAMILY_PRESETS = {
    "human_drama": {
        "label": "Human drama / moral conflict",
        "subreddits": [
            "AmItheAsshole", "AITAH", "relationship_advice", "offmychest",
            "confession", "tifu", "prorevenge", "MaliciousCompliance",
            "entitledparents", "BestofRedditorUpdates"
        ],
        "time_windows": ["day", "week", "month"],
        "min_upvotes": 1200,
        "min_body_length": 450,
        "quality_rules": "Prioritize a clear conflict, two arguable sides, escalation, and a first sentence that can stop a Shorts scroll."
    },
    "dark_curiosity": {
        "label": "Dark curiosity / scary true-feeling story",
        "subreddits": [
            "nosleep", "LetsNotMeet", "creepyencounters",
            "Glitch_in_the_Matrix", "UnresolvedMysteries", "TrueScaryStories"
        ],
        "time_windows": ["week", "month", "year"],
        "min_upvotes": 900,
        "min_body_length": 500,
        "quality_rules": "Prioritize an eerie hook, believable escalation, a memorable twist, and low gore/privacy risk."
    },
    "curiosity_facts": {
        "label": "Curiosity / facts / explainers",
        "subreddits": [
            "todayilearned", "explainlikeimfive", "Damnthatsinteresting",
            "mildlyinteresting", "science", "space", "InternetIsBeautiful"
        ],
        "time_windows": ["day", "week", "month"],
        "min_upvotes": 1800,
        "min_body_length": 250,
        "quality_rules": "Prioritize surprise, visual explainability, easy localization, and a fact that can be understood without niche context."
    },
    "football_culture": {
        "label": "Football culture / sports story",
        "subreddits": ["soccer", "football", "worldcup", "sports"],
        "time_windows": ["day", "week", "month"],
        "min_upvotes": 1000,
        "min_body_length": 120,
        "quality_rules": "Prioritize rights-safe discussion, player or fan drama, cultural identity, and stories that do not require match footage."
    },
    "internet_lore": {
        "label": "Internet lore / creator or community drama",
        "subreddits": [
            "OutOfTheLoop", "HobbyDrama", "SubredditDrama", "gaming",
            "InternetIsBeautiful", "technology"
        ],
        "time_windows": ["week", "month", "year"],
        "min_upvotes": 900,
        "min_body_length": 450,
        "quality_rules": "Prioritize a clear timeline, recognizable online conflict, broad audience comprehension, and low defamation/privacy risk."
    },
    "visual_comedy": {
        "label": "Visual social comedy / awkward real-life story",
        "subreddits": [
            "tifu", "talesfromyourserver", "confession",
            "mildlyinteresting", "entitledparents", "AmItheAsshole"
        ],
        "time_windows": ["day", "week", "month"],
        "min_upvotes": 900,
        "min_body_length": 300,
        "quality_rules": "Prioritize quick setup, embarrassment, social tension, and a punchline or twist that can land fast."
    }
}


FALLBACK_TOPIC_MIX_BY_NICHE = {
    "dark_curiosity_facts": [
        {"family": "dark_curiosity", "weight": 0.45},
        {"family": "curiosity_facts", "weight": 0.35},
        {"family": "internet_lore", "weight": 0.20},
    ],
    "spectacle_curiosity_drama": [
        {"family": "human_drama", "weight": 0.40},
        {"family": "curiosity_facts", "weight": 0.35},
        {"family": "internet_lore", "weight": 0.25},
    ],
    "science_curiosity_tech": [
        {"family": "curiosity_facts", "weight": 0.65},
        {"family": "internet_lore", "weight": 0.25},
        {"family": "dark_curiosity", "weight": 0.10},
    ],
    "human_drama_scandals": [
        {"family": "human_drama", "weight": 0.70},
        {"family": "internet_lore", "weight": 0.20},
        {"family": "visual_comedy", "weight": 0.10},
    ],
    "curiosities_football_drama": [
        {"family": "curiosity_facts", "weight": 0.40},
        {"family": "football_culture", "weight": 0.35},
        {"family": "human_drama", "weight": 0.25},
    ],
    "mystery_true_stories": [
        {"family": "dark_curiosity", "weight": 0.55},
        {"family": "internet_lore", "weight": 0.30},
        {"family": "curiosity_facts", "weight": 0.15},
    ],
    "comedy_football_drama": [
        {"family": "visual_comedy", "weight": 0.40},
        {"family": "football_culture", "weight": 0.30},
        {"family": "human_drama", "weight": 0.30},
    ],
}


WINDOW_SCORE_BONUS = {
    "day": 5,
    "week": 2,
    "month": -2,
    "year": -6,
}


STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "was", "were",
    "are", "you", "your", "have", "had", "has", "but", "not", "just",
    "aita", "aitah", "tifu", "because", "about", "after", "before",
}


def normalize_for_signature(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def topic_keyword_signature(title: str, body: str = "") -> str:
    normalized = normalize_for_signature(f"{title} {body[:600]}")
    words = [w for w in normalized.split() if len(w) > 3 and w not in STOPWORDS]
    return " ".join(sorted(set(words[:36]))[:16])


def keyword_signature_set(signature: str) -> set[str]:
    return {word for word in (signature or "").split() if word}


def keyword_signature_similarity(left: str, right: str) -> float:
    left_words = keyword_signature_set(left)
    right_words = keyword_signature_set(right)
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)


def story_signature(title: str, body: str = "") -> str:
    key = topic_keyword_signature(title, body)
    if not key:
        key = normalize_for_signature(f"{title} {body[:300]}")[:300]
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def post_velocity_metrics(post) -> dict:
    created_utc = float(getattr(post, "created_utc", 0) or 0)
    now_utc = datetime.now(timezone.utc).timestamp()
    age_hours = max((now_utc - created_utc) / 3600, 1.0) if created_utc else 9999.0
    ups = max(int(getattr(post, "score", 0) or 0), 0)
    comments = max(int(getattr(post, "num_comments", 0) or 0), 0)
    return {
        "age_hours": round(age_hours, 2),
        "upvotes_per_hour": round(ups / age_hours, 2),
        "comments_per_hour": round(comments / age_hours, 2),
    }


def velocity_bonus(metrics: dict, time_window: str) -> int:
    if time_window not in ("day", "week"):
        return 0
    uph = float(metrics.get("upvotes_per_hour", 0) or 0)
    cph = float(metrics.get("comments_per_hour", 0) or 0)
    bonus = 0
    if uph >= 150:
        bonus += 8
    elif uph >= 60:
        bonus += 5
    elif uph >= 20:
        bonus += 2
    if cph >= 12:
        bonus += 5
    elif cph >= 4:
        bonus += 2
    return min(bonus, 12)


def ai_quality_check(
    post_title: str,
    post_body: str,
    channel: dict,
    post_metadata: dict | None = None,
    topic_context: dict | None = None,
    duplicate_context: dict | None = None,
) -> dict:
    """
    Send the story to Gemini via VectorEngine for a structured quality assessment.

    Returns a dict with keys:
        verdict       : "PUBLISH" | "REWRITE" | "SKIP"
        niche_fit     : int 1-10
        hook_strength : int 1-10
        narrative_arc : int 1-10
        translation   : int 1-10
        viral_potential : int 1-10
        novelty         : int 1-10
        legal_risk      : int 1-10  (1=safe, 10=very risky)
        reason        : str
        hook_suggestion : str | None
    """
    if not AI_QUALITY_ENABLED:
        return {"verdict": "PUBLISH", "reason": "AI quality check disabled."}

    try:
        from vectorengine_client import call_gemini_json, VectorEngineError, load_dotenv_file
        load_dotenv_file(".env.vectorengine.local")
    except ImportError:
        print("  [quality] vectorengine_client not available — skipping AI check.")
        verdict = "PUBLISH" if AI_QUALITY_FAIL_OPEN else "SKIP"
        return {"verdict": verdict, "reason": "VectorEngine not available."}

    niche_label = channel.get("niche_label", "General entertainment")
    lang        = channel.get("lang", "en")
    handle      = channel.get("handle", "unknown")
    region      = channel.get("region", "unknown")
    topic_context = topic_context or {}
    post_metadata = post_metadata or {}
    duplicate_context = duplicate_context or {}

    # Truncate body to keep prompt within token limits
    body_preview = (post_body or "")[:800]
    topic_label = topic_context.get("label") or topic_context.get("family") or "Unspecified"
    topic_rules = topic_context.get("quality_rules") or "Use the channel profile and Reddit metrics."

    prompt = f"""
You are a YouTube content strategist. Evaluate this Reddit story for a specific channel.

CHANNEL PROFILE:
  Handle  : {handle}
  Language: {lang}
  Region  : {region}
  Niche   : {niche_label}

TOPIC FAMILY:
  Family : {topic_label}
  Rules  : {topic_rules}

REDDIT METRICS:
  Subreddit        : {post_metadata.get('subreddit', 'unknown')}
  Time window      : top/{post_metadata.get('time_window', 'unknown')}
  Upvotes          : {post_metadata.get('upvotes', 'unknown')}
  Comments         : {post_metadata.get('comments', 'unknown')}
  Comment/upvote % : {post_metadata.get('comment_ratio_pct', 'unknown')}
  Local virality   : {post_metadata.get('virality_score', 'unknown')}/100
  Age hours        : {post_metadata.get('age_hours', 'unknown')}
  Upvotes/hour     : {post_metadata.get('upvotes_per_hour', 'unknown')}
  Comments/hour    : {post_metadata.get('comments_per_hour', 'unknown')}
  Velocity bonus   : {post_metadata.get('velocity_bonus', 'unknown')}
  Topic fatigue    : -{post_metadata.get('fatigue_penalty', 'unknown')}
  Body length      : {post_metadata.get('body_length', 'unknown')} chars

DUPLICATE CONTEXT:
  Story signature  : {duplicate_context.get('story_signature', 'unknown')}
  Keyword signature: {duplicate_context.get('keyword_signature', 'unknown')}
  Known duplicate  : {duplicate_context.get('duplicate_reason', 'none')}

STORY:
  Title: {post_title}
  Body (first 800 chars): {body_preview}

SCORE each dimension from 1 (very poor) to 10 (excellent):
1. niche_fit       — Does this story match the channel niche perfectly?
2. hook_strength   — Is the first sentence strong enough to stop a Shorts scroll?
3. narrative_arc   — Does it have a clear conflict → escalation → resolution?
4. translation     — Will cultural context survive translation to {lang}? (10 = universal, 1 = deeply US-specific)
5. viral_potential — Based on Reddit metrics + story shape, can this trigger comments/retention on Shorts?
6. novelty         — Is it meaningfully different from common/repeated Reddit tropes?
7. duplicate_risk  — Risk this is a repeat/repost/same old trope (1 = fresh, 10 = likely duplicate)
8. legal_risk      — Risk of copyright/privacy/harmful content issues (1 = no risk, 10 = high risk)

VERDICT rules:
  PUBLISH  → niche_fit >= 6 AND hook_strength >= 6 AND viral_potential >= 6 AND novelty >= 5 AND duplicate_risk <= 6 AND legal_risk <= 5
  REWRITE  → niche_fit >= 5 AND viral_potential >= 6 AND legal_risk <= 6, but hook_strength < 6 or opening needs a stronger Shorts hook
  SKIP     → niche_fit < 5 OR viral_potential < 5 OR duplicate_risk > 7 OR legal_risk > 7

Return ONLY a JSON object, no markdown:
{{
  "verdict": "PUBLISH" | "REWRITE" | "SKIP",
  "niche_fit": <int>,
  "hook_strength": <int>,
  "narrative_arc": <int>,
  "translation": <int>,
  "viral_potential": <int>,
  "novelty": <int>,
  "duplicate_risk": <int>,
  "legal_risk": <int>,
  "topic_family": "<best matching family>",
  "shorts_hook_type": "<controversy|twist|mystery|fact|challenge|identity|other>",
  "reason": "<one sentence explaining verdict>",
  "hook_suggestion": "<rewritten opening line for Shorts, or null if PUBLISH/SKIP>"
}}
"""

    try:
        result = call_gemini_json(
            prompt=prompt,
            model=os.environ.get("AI_QUALITY_MODEL"),
            temperature=0.25,
            max_output_tokens=700,
        )
        verdict = result.get("verdict", "PUBLISH").upper()
        if verdict not in ("PUBLISH", "REWRITE", "SKIP"):
            verdict = "PUBLISH"
        result["verdict"] = verdict
        return result
    except VectorEngineError as e:
        verdict = "PUBLISH" if AI_QUALITY_FAIL_OPEN else "SKIP"
        print(f"  [quality] VectorEngine error — defaulting to {verdict}: {e}")
        return {"verdict": verdict, "reason": f"API error: {e}"}
    except Exception as e:
        verdict = "PUBLISH" if AI_QUALITY_FAIL_OPEN else "SKIP"
        print(f"  [quality] Unexpected error — defaulting to {verdict}: {e}")
        return {"verdict": verdict, "reason": f"Unexpected error: {e}"}


def fetch_top_comments(reddit, post_id, subreddit, limit=3):
    """Fetch top comments for a post, excluding AutoModerator."""
    try:
        submission = reddit.submission(id=post_id)
        submission.comments.replace_more(limit=0)
        comments = []
        count = 0
        for c in submission.comments:
            body = getattr(c, "body", "")
            author = str(getattr(c, "author", "")) if c.author else ""
            ups = getattr(c, "score", 0)

            if not body or not author:
                continue
            if author in ("AutoModerator", "[deleted]", "[removed]"):
                continue
            if len(body) < 10:
                continue

            comments.append({
                "id": count + 1,
                "username": f"u/{author}",
                "time": "3h ago",
                "body": body[:400],
                "upvotes": format_count(ups)
            })
            count += 1
            if count >= limit:
                break

        return comments
    except Exception as e:
        print(f"  Warning: could not fetch comments for {post_id}: {e}")
        return []


HISTORY_FILE = os.path.join(os.path.dirname(__file__), "published_history.json")


def load_history() -> dict[str, list[str]]:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"  Warning: could not load history: {e}")
    return {}


def history_posts(history: dict) -> dict:
    if isinstance(history.get("posts"), dict):
        return history["posts"]
    return history


def history_channels_for_post(history: dict, post_id: str) -> set[str]:
    posts = history_posts(history)
    record = posts.get(post_id)
    if isinstance(record, list):
        return set(record)
    if isinstance(record, dict):
        channels = record.get("channels", {})
        if isinstance(channels, dict):
            return set(channels.keys())
        if isinstance(channels, list):
            return set(channels)
    return set()


def history_has_post(history: dict, post_id: str, channel_id: str) -> bool:
    return channel_id in history_channels_for_post(history, post_id)


def history_has_signature(history: dict, signature: str, channel_id: str) -> bool:
    if not signature:
        return False
    for record in history_posts(history).values():
        if not isinstance(record, dict):
            continue
        if record.get("story_signature") != signature:
            continue
        channels = record.get("channels", {})
        if isinstance(channels, dict) and channel_id in channels:
            return True
        if isinstance(channels, list) and channel_id in channels:
            return True
    return False


def history_has_similar_keyword_signature(
    history: dict,
    keyword_signature: str,
    channel_id: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> tuple[bool, float]:
    best = 0.0
    if not keyword_signature:
        return False, best
    for record in history_posts(history).values():
        if not isinstance(record, dict):
            continue
        channels = record.get("channels", {})
        if isinstance(channels, dict) and channel_id not in channels:
            continue
        if isinstance(channels, list) and channel_id not in channels:
            continue
        if not isinstance(channels, (dict, list)):
            continue
        similarity = keyword_signature_similarity(keyword_signature, record.get("keyword_signature", ""))
        best = max(best, similarity)
        if similarity >= threshold:
            return True, similarity
    return False, best


def history_duplicate_reason(
    history: dict,
    post_id: str,
    signature: str,
    channel_id: str,
    keyword_signature: str = "",
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> str | None:
    if history_has_post(history, post_id, channel_id):
        return "already_published_post_id"
    if history_has_signature(history, signature, channel_id):
        return "already_published_story_signature"
    is_similar, similarity = history_has_similar_keyword_signature(
        history, keyword_signature, channel_id, threshold=similarity_threshold
    )
    if is_similar:
        return f"similar_story_keywords_{similarity:.2f}"
    return None


def parse_history_timestamp(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def recent_channel_records(history: dict, channel_id: str, limit: int = DEFAULT_TOPIC_FATIGUE_LOOKBACK) -> list[dict]:
    records = []
    for post_id, record in history_posts(history).items():
        if not isinstance(record, dict):
            continue
        channels = record.get("channels", {})
        if isinstance(channels, dict):
            channel_data = channels.get(channel_id)
            if channel_data is None:
                continue
            published_at = parse_history_timestamp(channel_data.get("published_at") if isinstance(channel_data, dict) else None)
        elif isinstance(channels, list) and channel_id in channels:
            published_at = None
        else:
            continue
        records.append({
            "post_id": post_id,
            "published_at": published_at,
            "topic_family": record.get("topic_family"),
            "title": record.get("title"),
        })
    records.sort(key=lambda item: item["published_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return records[:limit]


def topic_fatigue_penalty(topic_family: str, recent_records: list[dict]) -> int:
    if not topic_family or not recent_records:
        return 0
    recent_topics = [record.get("topic_family") for record in recent_records if record.get("topic_family")]
    if not recent_topics:
        return 0
    penalty = 0
    if recent_topics[0] == topic_family:
        penalty += 6
    penalty += min(8, recent_topics[:8].count(topic_family) * 2)
    return penalty


def normalize_history_for_save(history: dict) -> dict:
    if isinstance(history.get("posts"), dict):
        history.setdefault("version", 2)
        return history
    posts = {}
    for post_id, channels in history.items():
        if isinstance(channels, list):
            posts[post_id] = {"channels": {ch: {} for ch in channels}}
        elif isinstance(channels, dict):
            posts[post_id] = channels
    return {"version": 2, "posts": posts}


def save_history(post_id: str, channel_id: str, story: dict | None = None) -> None:
    history = normalize_history_for_save(load_history())
    posts = history.setdefault("posts", {})
    record = posts.setdefault(post_id, {})
    record.setdefault("channels", {})
    record["channels"].setdefault(channel_id, {})
    record["channels"][channel_id]["published_at"] = datetime.now(timezone.utc).isoformat()

    if story:
        record["title"] = story.get("title")
        record["subreddit"] = story.get("subreddit")
        record["url"] = story.get("url")
        record["story_signature"] = story.get("story_signature")
        record["keyword_signature"] = story.get("keyword_signature")
        record["topic_family"] = story.get("topic_family")
        record["topic_label"] = story.get("topic_label")
        record["time_window"] = story.get("time_window")
        record["virality_score"] = story.get("virality_score")
        record["base_virality_score"] = story.get("base_virality_score")
        record["velocity"] = story.get("velocity")
        record["fatigue_penalty"] = story.get("fatigue_penalty")
        record["ai_quality"] = story.get("ai_quality")

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"  Saved post {post_id} to history for channel {channel_id}")
    except Exception as e:
        print(f"  Warning: could not save history: {e}")


def channel_topic_mix(channel_config: dict | None) -> list[dict]:
    if not channel_config:
        return []
    configured = channel_config.get("topic_mix")
    if isinstance(configured, list) and configured:
        return configured
    return FALLBACK_TOPIC_MIX_BY_NICHE.get(channel_config.get("niche"), [])


def build_topic_sources(
    subreddits: list[str],
    time_filter: str,
    channel_config: dict | None = None,
    topic_family: str | None = None,
) -> list[dict]:
    mix = channel_topic_mix(channel_config)
    if topic_family:
        mix = [item for item in mix if item.get("family") == topic_family]

    if not mix:
        windows = ["week"] if time_filter == "auto" else [time_filter]
        return [{
            "family": topic_family or "legacy",
            "label": (channel_config or {}).get("niche_label", "Legacy subreddit scan"),
            "weight": 1.0,
            "subreddits": subreddits,
            "time_windows": windows,
            "min_upvotes": None,
            "min_body_length": None,
            "quality_rules": "Use the channel profile and Reddit metrics."
        }]

    sources = []
    for item in mix:
        family = item.get("family")
        preset = TOPIC_FAMILY_PRESETS.get(family)
        if not preset:
            continue
        windows = item.get("time_windows") or preset.get("time_windows", ["week"])
        if time_filter != "auto":
            windows = [time_filter]
        max_subreddits = int(item.get("max_subreddits", DEFAULT_MAX_SUBREDDITS_PER_TOPIC))
        max_windows = int(item.get("max_time_windows", DEFAULT_MAX_TIME_WINDOWS_PER_TOPIC))
        sources.append({
            "family": family,
            "label": preset["label"],
            "weight": float(item.get("weight", 1.0)),
            "subreddits": (item.get("subreddits") or preset["subreddits"])[:max_subreddits],
            "time_windows": [w for w in windows if w in VALID_TIME_FILTERS][:max_windows],
            "min_upvotes": item.get("min_upvotes", preset.get("min_upvotes")),
            "min_body_length": item.get("min_body_length", preset.get("min_body_length")),
            "quality_rules": item.get("quality_rules") or preset.get("quality_rules"),
        })
    return sources


def candidate_score(base_score: int, topic_weight: float, time_window: str) -> int:
    topic_boost = round(max(topic_weight, 0.0) * 12)
    return max(0, min(120, base_score + topic_boost + WINDOW_SCORE_BONUS.get(time_window, 0)))


def fetch_best_story(subreddits, time_filter="auto", min_upvotes=1000,
                     min_body_length=300, comment_limit=3, channel_id="default",
                     channel_config=None, skip_rank=0, max_ai_candidates=None,
                     candidate_limit=DEFAULT_CANDIDATE_LIMIT, topic_family=None,
                     similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD):
    """
    Search topic-family sources for the most viral post, then run a bounded AI
    quality gate (Gemini via VectorEngine) to confirm channel fit, novelty, and
    Shorts potential.

    Parameters
    ----------
    subreddits     : list[str]  - subreddit names (without r/)
    time_filter    : str        - 'auto' | 'day' | 'week' | 'month' | 'year'
    min_upvotes    : int        - minimum upvote threshold
    min_body_length: int        - minimum post body length in characters
    comment_limit  : int        - number of top comments to fetch
    channel_id     : str        - active channel index for duplicate protection
    channel_config : dict|None  - full channel dict from channels.json (for AI check)
    skip_rank      : int        - skip the top-N AI-approved candidates (for multi-slot daily publishing)
    max_ai_candidates: int      - hard cap on Gemini quality checks per scrape
    candidate_limit: int        - top posts fetched per subreddit/window source
    topic_family   : str|None   - force one topic family for experiments
    similarity_threshold: float - keyword overlap threshold for semantic dedupe

    Returns
    -------
    dict  - story payload ready for story_data.json
    """
    reddit = get_reddit()
    history = load_history()
    max_ai_candidates = DEFAULT_MAX_AI_CANDIDATES if max_ai_candidates is None else max_ai_candidates

    # ── Phase 1: collect candidates across topic families and time windows ─
    candidates = []
    seen_post_ids = set()
    seen_signatures = set()
    seen_keyword_signatures = []
    recent_records = recent_channel_records(history, channel_id)
    sources = build_topic_sources(
        subreddits=subreddits,
        time_filter=time_filter,
        channel_config=channel_config,
        topic_family=topic_family,
    )

    print(f"Topic mode: {len(sources)} source family/families | candidate limit/source={candidate_limit}")

    for source in sources:
        windows = source["time_windows"] or ["week"]
        source_min_upvotes = max(min_upvotes, int(source["min_upvotes"] or min_upvotes))
        source_min_body = max(min_body_length, int(source["min_body_length"] or min_body_length))
        for window in windows:
            for sub_name in source["subreddits"]:
                print(f"  Scanning [{source['family']}] r/{sub_name} (top/{window})...")
                try:
                    subreddit = reddit.subreddit(sub_name)
                    for post in subreddit.top(time_filter=window, limit=candidate_limit):
                        if post.stickied:
                            continue
                        body = post.selftext or ""
                        if body in ("[removed]", "[deleted]"):
                            continue
                        if post.score < source_min_upvotes:
                            continue
                        if len(body) < source_min_body:
                            continue

                        keyword_signature = topic_keyword_signature(post.title, body)
                        signature = story_signature(post.title, body)
                        duplicate_reason = history_duplicate_reason(
                            history, post.id, signature, channel_id, keyword_signature, similarity_threshold
                        )
                        if duplicate_reason:
                            print(f"    skip duplicate ({duplicate_reason}) | {post.title[:55]}")
                            continue
                        if post.id in seen_post_ids or signature in seen_signatures:
                            continue
                        if any(
                            keyword_signature_similarity(keyword_signature, seen) >= similarity_threshold
                            for seen in seen_keyword_signatures
                        ):
                            continue

                        base_score = virality_score(post)
                        velocity = post_velocity_metrics(post)
                        velocity_points = velocity_bonus(velocity, window)
                        fatigue_penalty = topic_fatigue_penalty(source["family"], recent_records)
                        weighted_score = max(
                            0,
                            candidate_score(base_score, source["weight"], window)
                            + velocity_points
                            - fatigue_penalty,
                        )
                        seen_post_ids.add(post.id)
                        seen_signatures.add(signature)
                        seen_keyword_signatures.append(keyword_signature)
                        print(f"    [{weighted_score:3d}/{base_score:3d}] {post.score:>6} ups | "
                              f"{post.num_comments:>5} comments | {post.title[:55]}")
                        candidates.append({
                            "score": weighted_score,
                            "base_score": base_score,
                            "velocity_bonus": velocity_points,
                            "fatigue_penalty": fatigue_penalty,
                            "velocity": velocity,
                            "post": post,
                            "topic": source,
                            "time_window": window,
                            "story_signature": signature,
                            "keyword_signature": keyword_signature,
                        })

                except Exception as e:
                    print(f"  Error scanning r/{sub_name}: {e}")
                    continue

    if not candidates:
        print("No suitable story found.")
        return None

    # Sort descending by weighted score; try best candidate first
    candidates.sort(key=lambda item: item["score"], reverse=True)

    # ── Phase 2: AI quality gate — bounded by max_ai_candidates ────────────
    chosen_post  = None
    chosen_score = -1
    ai_result    = {}
    chosen_candidate = None
    chosen_rank = None
    approved_count = 0   # counts how many candidates passed AI check
    ai_budget = len(candidates) if not AI_QUALITY_ENABLED else max(1, max_ai_candidates + skip_rank)
    ai_candidates = candidates[:ai_budget]

    print(f"\nAI quality budget: checking {len(ai_candidates)} of {len(candidates)} candidate(s)")

    for rank, candidate in enumerate(ai_candidates):
        score = candidate["score"]
        post = candidate["post"]
        body = post.selftext or ""
        ups = max(post.score, 1)
        topic = candidate["topic"]
        print(f"\n🤖 [AI quality check] #{rank+1} candidate: {post.title[:60]}")
        qc = ai_quality_check(
            post_title=post.title,
            post_body=body,
            channel=channel_config or {},
            post_metadata={
                "subreddit": f"r/{post.subreddit}",
                "time_window": candidate["time_window"],
                "upvotes": post.score,
                "comments": post.num_comments,
                "comment_ratio_pct": round((post.num_comments / ups) * 100, 2),
                "virality_score": candidate["base_score"],
                "velocity_bonus": candidate["velocity_bonus"],
                "fatigue_penalty": candidate["fatigue_penalty"],
                "age_hours": candidate["velocity"].get("age_hours"),
                "upvotes_per_hour": candidate["velocity"].get("upvotes_per_hour"),
                "comments_per_hour": candidate["velocity"].get("comments_per_hour"),
                "body_length": len(body),
            },
            topic_context={
                "family": topic["family"],
                "label": topic["label"],
                "quality_rules": topic.get("quality_rules"),
            },
            duplicate_context={
                "story_signature": candidate["story_signature"],
                "keyword_signature": candidate["keyword_signature"],
                "duplicate_reason": "none",
            },
        )
        verdict = qc.get("verdict", "PUBLISH")
        print(f"   Verdict: {verdict} | "
              f"niche={qc.get('niche_fit','?')} "
              f"hook={qc.get('hook_strength','?')} "
              f"arc={qc.get('narrative_arc','?')} "
              f"translate={qc.get('translation','?')} "
              f"viral={qc.get('viral_potential','?')} "
              f"novelty={qc.get('novelty','?')} "
              f"dupe={qc.get('duplicate_risk','?')} "
              f"risk={qc.get('legal_risk','?')}")
        print(f"   Reason : {qc.get('reason', '')}")

        if verdict == "SKIP":
            print("   ⛔ Skipped by AI — trying next candidate...")
            continue

        # This candidate passed AI check — count it
        if approved_count < skip_rank:
            print(f"   ⏭️  Slot offset: skipping approved candidate #{approved_count+1} (reserved for earlier slot)")
            approved_count += 1
            continue

        # PUBLISH or REWRITE at the right slot position — take it
        chosen_post  = post
        chosen_score = score
        ai_result    = qc
        chosen_candidate = candidate
        chosen_rank = rank + 1
        break

    if not chosen_post:
        print("\n❌ No candidate passed within the AI quality budget.")
        return None

    print(f"\n✅ Story approved (virality={chosen_score}, verdict={ai_result.get('verdict')}):")
    print(f"   r/{chosen_post.subreddit} — {chosen_post.title[:70]}")
    print(f"   {format_count(chosen_post.score)} upvotes | "
          f"{format_count(chosen_post.num_comments)} comments")
    print(f"   topic={chosen_candidate['topic']['family']} | window=top/{chosen_candidate['time_window']}")

    comments = fetch_top_comments(
        reddit, chosen_post.id, str(chosen_post.subreddit), limit=comment_limit
    )

    # If AI suggested a better hook, store it so translator_tts.py can use it
    hook_override = ai_result.get("hook_suggestion") or None

    return {
        "subreddit": f"r/{chosen_post.subreddit}",
        "title": chosen_post.title,
        "author": f"u/{chosen_post.author}" if chosen_post.author else "u/deleted",
        "body": chosen_post.selftext,
        "upvotes": format_count(chosen_post.score),
        "comments_count": format_count(chosen_post.num_comments),
        "virality_score": chosen_score,
        "base_virality_score": chosen_candidate["base_score"],
        "velocity_bonus": chosen_candidate["velocity_bonus"],
        "fatigue_penalty": chosen_candidate["fatigue_penalty"],
        "velocity": chosen_candidate["velocity"],
        "topic_family": chosen_candidate["topic"]["family"],
        "topic_label": chosen_candidate["topic"]["label"],
        "time_window": chosen_candidate["time_window"],
        "story_signature": chosen_candidate["story_signature"],
        "keyword_signature": chosen_candidate["keyword_signature"],
        "candidate_rank": chosen_rank,
        "candidate_pool_size": len(candidates),
        "ai_candidate_budget": len(ai_candidates),
        "ai_quality": ai_result,
        "hook_override": hook_override,
        "url": f"https://reddit.com{chosen_post.permalink}",
        "post_id": chosen_post.id,
        "comments": comments
    }


def load_channel_config(channel_id=None):
    """
    Load channel strategy from channels.json.
    Returns config for the given channel ID, or first channel if not specified.
    """
    config_path = os.path.join(os.path.dirname(__file__), "channels.json")
    if not os.path.exists(config_path):
        return None

    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)

    channels = data.get("channels", [])
    if not channels:
        return None

    if channel_id:
        for ch in channels:
            if ch.get("id") == channel_id or ch.get("handle") == channel_id:
                return ch

    return channels[0]


# ─────────────────────────────────────────────
#  CLI entry point
#
#  Usage:
#    python3 scraper.py                          → uses channels.json channel #1
#    python3 scraper.py nosleep                  → specific subreddit
#    python3 scraper.py --channel acc4           → channel from channels.json
#    python3 scraper.py --channel acc4 --time auto
#    python3 scraper.py --channel acc4 --topic-family human_drama
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ChonkerTalks Reddit Scraper")
    parser.add_argument("subreddit", nargs="?", default=None,
                        help="Subreddit name (overrides channels.json)")
    parser.add_argument("--channel", "-c", default=None,
                        help="Channel ID from channels.json (e.g. acc1, acc4)")
    parser.add_argument("--time", "-t", default="auto",
                        choices=["auto", "day", "week", "month", "year"],
                        help="Time filter for top posts. auto uses topic-family windows (default: auto)")
    parser.add_argument("--min-upvotes", "-u", type=int, default=1000,
                        help="Minimum upvotes threshold (default: 1000)")
    parser.add_argument("--output", "-o", default="story_data.json",
                        help="Output JSON file (default: story_data.json)")
    parser.add_argument("--video-slot", "-s", type=int, default=1,
                        help="Which video slot of the day (1=first/morning, 2=second/evening). "
                             "Slot N skips the top N-1 AI-approved candidates so each slot "
                             "gets a unique story. (default: 1)")
    parser.add_argument("--topic-family", default=None,
                        help="Force one topic family, e.g. human_drama, dark_curiosity, curiosity_facts.")
    parser.add_argument("--max-ai-candidates", type=int, default=DEFAULT_MAX_AI_CANDIDATES,
                        help=f"Maximum Gemini quality checks per scrape (default: {DEFAULT_MAX_AI_CANDIDATES})")
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT,
                        help=f"Reddit top posts fetched per subreddit/window source (default: {DEFAULT_CANDIDATE_LIMIT})")
    parser.add_argument("--similarity-threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD,
                        help=f"Keyword-overlap duplicate threshold, 0-1 (default: {DEFAULT_SIMILARITY_THRESHOLD})")
    args = parser.parse_args()

    # Determine subreddits to scan
    channel = None
    if args.subreddit:
        subreddits = [args.subreddit]
        print(f"Mode: single subreddit → r/{args.subreddit}")
    else:
        channel = load_channel_config(args.channel)
        if channel:
            subreddits = channel.get("subreddits", ["AskReddit"])
            print(f"Mode: channel strategy → {channel.get('handle')} "
                  f"({channel.get('niche_label')})")
            print(f"Subreddits: {', '.join(f'r/{s}' for s in subreddits)}")
        else:
            subreddits = ["AmItheAsshole", "nosleep", "confession"]
            print("Mode: fallback defaults")

    print(f"Time filter: {args.time} | Min upvotes: {args.min_upvotes} | Max AI candidates: {args.max_ai_candidates}\n")

    channel_key = args.channel or "default"
    skip_rank = max(0, args.video_slot - 1)   # slot 1→skip 0, slot 2→skip 1, etc.
    if skip_rank:
        print(f"Video slot #{args.video_slot}: will skip {skip_rank} already-approved candidate(s).")
    story = fetch_best_story(
        subreddits=subreddits,
        time_filter=args.time,
        min_upvotes=args.min_upvotes,
        channel_id=channel_key,
        channel_config=channel if not args.subreddit else {},
        skip_rank=skip_rank,
        max_ai_candidates=args.max_ai_candidates,
        candidate_limit=args.candidate_limit,
        topic_family=args.topic_family,
        similarity_threshold=args.similarity_threshold
    )

    if story:
        output_path = os.path.join(os.path.dirname(__file__), args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(story, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Saved → {output_path}")
        save_history(story["post_id"], channel_key, story)
    else:
        print("\n❌ No story found. Try a different subreddit or time filter.")
        sys.exit(1)
