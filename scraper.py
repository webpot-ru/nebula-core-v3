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


def trim_text_at_word_boundary(text: str, max_chars: int) -> tuple[str, bool]:
    value = str(text or "").strip()
    if max_chars <= 0 or len(value) <= max_chars:
        return value, False

    clipped = value[:max_chars].rstrip()
    boundary = max(clipped.rfind("\n"), clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
    if boundary >= max(120, int(max_chars * 0.55)):
        clipped = clipped[: boundary + 1].rstrip()
    else:
        space = clipped.rfind(" ")
        if space >= max(80, int(max_chars * 0.65)):
            clipped = clipped[:space].rstrip()
    return clipped.rstrip(" .,;:") + "...", True


def apply_story_length_limits(
    story: dict,
    *,
    max_body_chars: int | None = None,
    max_comments: int | None = None,
    format_intent: str | None = None,
) -> dict:
    if not story:
        return story

    limited = dict(story)
    trim_metadata = {
        "format_intent": format_intent or "unspecified",
        "body_original_chars": len(str(story.get("body") or "")),
        "body_max_chars": max_body_chars,
        "comments_original_count": len(story.get("comments") or []),
        "comments_max_count": max_comments,
        "body_trimmed": False,
        "comments_trimmed": False,
    }

    if max_body_chars is not None and max_body_chars > 0:
        body, was_trimmed = trim_text_at_word_boundary(str(story.get("body") or ""), max_body_chars)
        limited["body"] = body
        trim_metadata["body_trimmed"] = was_trimmed
        trim_metadata["body_final_chars"] = len(body)

    if max_comments is not None and max_comments >= 0:
        comments = list(story.get("comments") or [])
        limited["comments"] = comments[:max_comments]
        trim_metadata["comments_trimmed"] = len(comments) > len(limited["comments"])
        trim_metadata["comments_final_count"] = len(limited["comments"])

    if trim_metadata["body_trimmed"] or trim_metadata["comments_trimmed"]:
        limited["content_limits"] = trim_metadata
        print(
            "Applied story length limits: "
            f"format={trim_metadata['format_intent']} "
            f"body={trim_metadata.get('body_final_chars', trim_metadata['body_original_chars'])}/"
            f"{trim_metadata['body_original_chars']} chars "
            f"comments={trim_metadata.get('comments_final_count', trim_metadata['comments_original_count'])}/"
            f"{trim_metadata['comments_original_count']}"
        )
    return limited


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
        "quality_rules": (
            "Prioritize intimate first-person conflict, a clear 'who is right?' question, two arguable sides, social stakes, escalation, and a first screen that can stop a Shorts scroll. "
            "Reject news, product announcements, gaming/tech updates, link-only discussions, broad community debates, generic advice prompts, and posts without a standalone human story."
        )
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
        "quality_rules": "Prioritize an eerie first screen, believable escalation, a memorable reveal/twist, strong atmosphere, and low gore/privacy risk. Reject vague creepypasta with no concrete incident, excessive gore, and stories that rely only on shock."
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
        "quality_rules": "Prioritize counterintuitive facts with a clean 'wait, what?' hook, visual explainability, easy localization, and a story/explanation arc. Reject thin trivia, dry announcements, niche technical details, and facts that need unavailable footage."
    },
    "football_culture": {
        "label": "Football culture / sports story",
        "subreddits": ["soccer", "football", "worldcup", "sports"],
        "time_windows": ["day", "week", "month"],
        "min_upvotes": 1000,
        "min_body_length": 120,
        "quality_rules": "Prioritize rights-safe player arcs, fan drama, cultural identity, rivalry, underdog/comeback angles, and stories that can work without match footage. Reject score-only news, transfer rumors with no human angle, and posts that need licensed clips to make sense."
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
        "quality_rules": "Prioritize a clean timeline, recognizable online conflict, creator/community stakes, lore that can be explained fast, broad audience comprehension, and low defamation/privacy risk. Reject niche forum drama, gaming-server admin stories, and posts where the appeal is only fandom-specific."
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
        "quality_rules": "Prioritize quick setup, visible social tension, embarrassment, role-play potential, and a punchline/twist that can land fast. Reject jokes that only work in English, screenshot/image-dependent posts, and stories with no clear payoff."
    }
}


FALLBACK_TOPIC_MIX_BY_NICHE = {
    "dark_curiosity_facts": [
        {"family": "dark_curiosity", "weight": 0.55},
        {"family": "curiosity_facts", "weight": 0.45},
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


FORMAT_INTENT_RULES = {
    "auto": (
        "Decide whether the story is better as Shorts, long-form, or both. "
        "Approve only if it has either a sharp Shorts cut or enough depth for a long-form episode."
    ),
    "shorts": (
        "This will be a vertical Shorts test. Require a strong first 1-2 seconds, a self-contained 30-90 second cut, "
        "minimal setup, one clear emotional/factual payoff, and comment bait that feels natural. "
        "Skip slow-burn stories that only become interesting after long context."
    ),
    "long": (
        "This will be a horizontal long-form video. Require enough plot, timeline, stakes, explanation depth, or comment debate "
        "for an 8-18 minute episode. Skip thin facts and one-joke stories even if they work as Shorts."
    ),
}


CHANNEL_PRODUCER_PRESETS = {
    "ru": {
        "audience_job": "Give Russian-speaking viewers a dark, surprising, easy-to-retell story or fact without drifting into gaming/news filler.",
        "must_feel_like": "mysterious, specific, tense, but not exploitative or political",
        "winning_bets": "strange real-feeling incidents, eerie personal encounters, unsettling facts with a clean reveal",
        "weak_topic_traps": "generic scary fiction, Minecraft/gaming-server drama, dry trivia, broad tech/news updates, politics-heavy material",
    },
    "es-419": {
        "audience_job": "Give LATAM viewers an emotional social conflict they can judge, argue about, and retell like a mini telenovela.",
        "must_feel_like": "dramatic, intimate, conversational, socially charged",
        "winning_bets": "family scandal, relationship betrayal, entitlement, public humiliation, moral choice with two sides",
        "weak_topic_traps": "flat advice posts, low-stakes roommate chores, US-only culture context, stories with no emotional turn",
    },
    "pt-br": {
        "audience_job": "Give Brazilian viewers energetic curiosity, football culture, or emotional personal stories with a clear payoff.",
        "must_feel_like": "fast, expressive, surprising, culturally easy to localize",
        "winning_bets": "unknown facts, football arcs, fan drama, emotional twists, high-energy social conflict",
        "weak_topic_traps": "dry statistics, rights-dependent match clips, weak Reddit drama, slow setup without payoff",
    },
    "de": {
        "audience_job": "Give German-speaking viewers credible curiosity, experiments, tech/science explainers, or strange facts that feel worth learning.",
        "must_feel_like": "clear, smart, precise, not overhyped",
        "winning_bets": "counterintuitive facts, explainable experiments, tech/internet consequences, strange discoveries",
        "weak_topic_traps": "sensationalism without evidence, vague creepypasta, celebrity gossip, low-value trivia",
    },
    "fr": {
        "audience_job": "Give French-speaking viewers a mystery, dossier, true-story angle, or pop/internet lore with atmosphere and structure.",
        "must_feel_like": "intriguing, stylish, well-framed, slightly investigative",
        "winning_bets": "mystery timelines, creator/community lore, strange true-feeling events, pop-culture dossiers",
        "weak_topic_traps": "thin horror, niche gaming posts, gossip without timeline, stories that need too much explanation",
    },
    "it": {
        "audience_job": "Give Italian viewers expressive social comedy, football identity, food/culture tension, or relationship drama that can be performed.",
        "must_feel_like": "expressive, visual, playful, emotionally legible",
        "winning_bets": "awkward social scenes, football/fan identity, relationship conflict, family/culture friction, punchy reversals",
        "weak_topic_traps": "text-only jokes with no visual scene, weak facts, slow lore, English-only wordplay",
    },
    "en": {
        "audience_job": "Give English-speaking viewers spectacle curiosity, internet lore, creator drama, or a story hook strong enough to survive heavy competition.",
        "must_feel_like": "high-concept, instantly clear, specific, not another generic Reddit read",
        "winning_bets": "weird experiments, creator/community conflict, internet-lore timelines, shocking but credible story turns",
        "weak_topic_traps": "ordinary AITA filler, low-stakes chores, overused Reddit tropes, topics already saturated by larger channels",
    },
}


TOPIC_BET_PRESETS = {
    "human_drama": {
        "content_bet": "moral court / social conflict",
        "why_click": "The viewer immediately wants to decide who is wrong.",
        "why_stay": "The story escalates, reveals new context, and makes the viewer reconsider.",
        "shorts_shape": "one conflict, one accusation, one twist, one comment-bait question",
        "long_shape": "case file: setup, motives, escalation, comments/community verdict, final producer take",
        "voice_direction": "expressive narrator plus distinct comment voices; character voices work for opposing sides if not caricatured",
        "reject_if": "the conflict is low-stakes, one-sided, generic, advice-only, or depends on missing comments/screenshots",
    },
    "dark_curiosity": {
        "content_bet": "mystery / eerie incident",
        "why_click": "The viewer wants to know what happened or what the disturbing detail means.",
        "why_stay": "Specific details accumulate toward a reveal, twist, or unresolved question.",
        "shorts_shape": "one eerie claim, two concrete details, one reveal/question",
        "long_shape": "timeline: normal situation, anomaly, escalation, theories, unresolved ending",
        "voice_direction": "dramatic narrator; subtle character/special voice can help horror, but avoid parody",
        "reject_if": "it is vague creepypasta, pure gore, politics-heavy, privacy-invasive, or lacks concrete detail",
    },
    "curiosity_facts": {
        "content_bet": "counterintuitive fact / explainer",
        "why_click": "The viewer sees a surprising 'wait, what?' claim.",
        "why_stay": "The explanation resolves the surprise in simple steps.",
        "shorts_shape": "claim, visual mental image, explanation, punchline/fact payoff",
        "long_shape": "mini-documentary: question, context, mechanism, examples, consequence",
        "voice_direction": "clear energetic narrator; character voices only if the fact has a scene or dialogue",
        "reject_if": "it is dry trivia, too technical, source/link dependent, or cannot be visualized from text",
    },
    "football_culture": {
        "content_bet": "football identity / fan drama / player arc",
        "why_click": "The viewer recognizes rivalry, injustice, comeback, or cultural pride.",
        "why_stay": "The story has stakes beyond a score: identity, loyalty, betrayal, pressure, redemption.",
        "shorts_shape": "one football tension, one emotional stake, one reversal",
        "long_shape": "rights-safe documentary without match footage: context, character, conflict, fallout",
        "voice_direction": "energetic local narrator; comments can sound like fans from different sides",
        "reject_if": "it needs match clips, is only transfer news, or has no human/cultural angle",
    },
    "internet_lore": {
        "content_bet": "internet lore / creator-community timeline",
        "why_click": "The viewer senses there is a bigger story behind a meme, creator, fandom, or online conflict.",
        "why_stay": "The timeline becomes clear and reveals stakes outsiders can understand.",
        "shorts_shape": "what happened, why people cared, the twist/fallout",
        "long_shape": "dossier: origin, escalation, key players, community reaction, aftermath",
        "voice_direction": "curious narrator; character voices can separate creator/community/comment perspectives",
        "reject_if": "it is narrow fandom drama, gaming-server admin minutiae, defamation-prone, or too hard to explain fast",
    },
    "visual_comedy": {
        "content_bet": "performable social comedy",
        "why_click": "The viewer instantly imagines the awkward scene.",
        "why_stay": "The social tension or embarrassment lands with a payoff.",
        "shorts_shape": "scene, awkward pressure, escalation, punchline/reversal",
        "long_shape": "compilation or social-experiment style episode, not a single thin joke",
        "voice_direction": "character voices are useful; make roles distinct but believable",
        "reject_if": "the joke is wordplay-only, culturally untranslatable, screenshot-dependent, or has no visible scene",
    },
}


def channel_producer_context(channel: dict | None) -> dict:
    if not channel:
        return CHANNEL_PRODUCER_PRESETS["en"]
    lang = str(channel.get("lang") or "en").lower()
    normalized = lang.replace("_", "-")
    if normalized in CHANNEL_PRODUCER_PRESETS:
        return CHANNEL_PRODUCER_PRESETS[normalized]
    base = normalized.split("-", 1)[0]
    return CHANNEL_PRODUCER_PRESETS.get(base, CHANNEL_PRODUCER_PRESETS["en"])


def topic_bet_context(topic_family: str | None) -> dict:
    return TOPIC_BET_PRESETS.get(topic_family or "", {
        "content_bet": "general entertainment topic",
        "why_click": "The viewer immediately understands why this is worth watching.",
        "why_stay": "The story develops beyond the title.",
        "shorts_shape": "hook, escalation, payoff",
        "long_shape": "structured episode with enough depth for retention",
        "voice_direction": "use a voice style that supports the channel promise without sounding generic",
        "reject_if": "the idea is generic, source-dependent, repetitive, or not tied to the channel promise",
    })


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


def score_int(value, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(10, parsed))


def hook_evidence_items(ai_result: dict) -> list[dict]:
    raw = ai_result.get("hook_evidence")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        quote = ai_result.get("hook_evidence_quote")
        field = ai_result.get("hook_evidence_field")
        if quote:
            raw = [{"field": field or "unknown", "quote": quote}]
        else:
            raw = []
    items = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        if not quote:
            continue
        items.append({
            "field": str(item.get("field") or "unknown").strip(),
            "quote": quote[:240],
            "why_it_matters": str(item.get("why_it_matters") or "").strip()[:240],
        })
    return items


def has_hook_evidence(ai_result: dict) -> bool:
    return bool(hook_evidence_items(ai_result))


def producer_quality_score(local_score: int, ai_result: dict) -> float:
    positive_keys = (
        "niche_fit",
        "hook_strength",
        "narrative_arc",
        "discussion_potential",
        "format_fit",
        "translation",
        "viral_potential",
        "novelty",
        "character_voice_fit",
    )
    risk_keys = (
        "slop_risk",
        "source_dependency_risk",
        "duplicate_risk",
        "legal_risk",
    )
    positives = sum(score_int(ai_result.get(key), 5) for key in positive_keys)
    risks = sum(score_int(ai_result.get(key), 5) for key in risk_keys)
    verdict = str(ai_result.get("verdict") or "").upper()
    verdict_bonus = 14 if verdict == "PUBLISH" else 6 if verdict == "REWRITE" else -30
    evidence_bonus = 8 if has_hook_evidence(ai_result) else -12
    format_bonus = 4 if str(ai_result.get("format_recommendation") or "").lower() in {"shorts", "long", "both"} else 0
    return round((local_score * 0.35) + (positives * 4.0) - (risks * 3.2) + verdict_bonus + evidence_bonus + format_bonus, 2)


def producer_queue_entry(candidate: dict, ai_rank: int, ai_result: dict) -> dict:
    post = candidate["post"]
    local_score = int(candidate.get("score") or 0)
    producer_score = producer_quality_score(local_score, ai_result)
    return {
        "ai_rank": ai_rank,
        "producer_score": producer_score,
        "local_score": local_score,
        "base_virality_score": candidate.get("base_score"),
        "verdict": ai_result.get("verdict"),
        "subreddit": f"r/{post.subreddit}",
        "post_id": post.id,
        "title": post.title,
        "url": f"https://reddit.com{post.permalink}",
        "upvotes": post.score,
        "comments": post.num_comments,
        "topic_family": candidate["topic"]["family"],
        "topic_label": candidate["topic"]["label"],
        "time_window": candidate["time_window"],
        "story_signature": candidate["story_signature"],
        "keyword_signature": candidate["keyword_signature"],
        "velocity": candidate.get("velocity"),
        "velocity_bonus": candidate.get("velocity_bonus"),
        "fatigue_penalty": candidate.get("fatigue_penalty"),
        "scores": {
            "niche_fit": ai_result.get("niche_fit"),
            "hook_strength": ai_result.get("hook_strength"),
            "narrative_arc": ai_result.get("narrative_arc"),
            "discussion_potential": ai_result.get("discussion_potential"),
            "format_fit": ai_result.get("format_fit"),
            "translation": ai_result.get("translation"),
            "viral_potential": ai_result.get("viral_potential"),
            "novelty": ai_result.get("novelty"),
            "character_voice_fit": ai_result.get("character_voice_fit"),
            "slop_risk": ai_result.get("slop_risk"),
            "source_dependency_risk": ai_result.get("source_dependency_risk"),
            "duplicate_risk": ai_result.get("duplicate_risk"),
            "legal_risk": ai_result.get("legal_risk"),
        },
        "format_recommendation": ai_result.get("format_recommendation"),
        "content_bet": ai_result.get("content_bet"),
        "audience_job_fit": ai_result.get("audience_job_fit"),
        "first_screen_promise": ai_result.get("first_screen_promise"),
        "first_screen_text": ai_result.get("first_screen_text"),
        "packaging_thesis": ai_result.get("packaging_thesis"),
        "why_now": ai_result.get("why_now"),
        "shorts_cut": ai_result.get("shorts_cut"),
        "longform_angle": ai_result.get("longform_angle"),
        "producer_angle": ai_result.get("producer_angle"),
        "hook_suggestion": ai_result.get("hook_suggestion"),
        "hook_evidence": hook_evidence_items(ai_result),
        "reason": ai_result.get("reason"),
    }


def write_producer_queue(
    output_path: str | None,
    *,
    channel_id: str,
    format_intent: str,
    candidates_total: int,
    ai_budget: int,
    skip_rank: int,
    entries: list[dict],
    chosen_entry: dict | None,
) -> None:
    if not output_path:
        return
    payload = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "channel_id": channel_id,
        "format_intent": format_intent,
        "candidates_total": candidates_total,
        "ai_candidate_budget": ai_budget,
        "skip_rank": skip_rank,
        "selected_post_id": chosen_entry.get("post_id") if chosen_entry else None,
        "selected_producer_score": chosen_entry.get("producer_score") if chosen_entry else None,
        "entries": entries,
    }
    path = output_path
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(__file__), path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  Saved producer queue → {path}")


def ai_quality_check(
    post_title: str,
    post_body: str,
    channel: dict,
    post_metadata: dict | None = None,
    topic_context: dict | None = None,
    duplicate_context: dict | None = None,
    format_intent: str | None = None,
) -> dict:
    """
    Send the story to Gemini for a structured quality assessment.

    Returns a dict with keys:
        verdict       : "PUBLISH" | "REWRITE" | "SKIP"
        niche_fit     : int 1-10
        hook_strength : int 1-10
        narrative_arc : int 1-10
        translation   : int 1-10
        viral_potential : int 1-10
        format_fit      : int 1-10
        discussion_potential : int 1-10
        character_voice_fit  : int 1-10
        slop_risk       : int 1-10  (1=original and specific, 10=generic AI-slop/template bait)
        source_dependency_risk : int 1-10
        novelty         : int 1-10
        legal_risk      : int 1-10  (1=safe, 10=very risky)
        reason        : str
        hook_suggestion : str | None
        hook_evidence : list[dict] with exact source quote(s) for the hook
    """
    if not AI_QUALITY_ENABLED:
        return {"verdict": "PUBLISH", "reason": "AI quality check disabled."}

    try:
        from vectorengine_client import call_gemini_json, VectorEngineError, load_dotenv_file
        load_dotenv_file(".env.gemini.local")
        load_dotenv_file(".env.vectorengine.local")
    except ImportError:
        print("  [quality] vectorengine_client not available — skipping AI check.")
        verdict = "PUBLISH" if AI_QUALITY_FAIL_OPEN else "SKIP"
        return {"verdict": verdict, "reason": "Gemini client not available."}

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
    topic_family = topic_context.get("family")
    topic_rules = topic_context.get("quality_rules") or "Use the channel profile and Reddit metrics."
    format_intent = (format_intent or "auto").strip().lower()
    format_rules = FORMAT_INTENT_RULES.get(format_intent, FORMAT_INTENT_RULES["auto"])
    producer_context = channel_producer_context(channel)
    topic_bet = topic_bet_context(topic_family)
    channel_exclusions = channel_topic_exclusions(channel)
    exclusion_text = ", ".join(channel_exclusions) if channel_exclusions else "none configured"

    prompt = f"""
You are a senior YouTube producer and audience-development strategist.
Your job is NOT to be nice to the candidate. Your job is to protect the channel from weak, generic, repetitive, or hard-to-retain topics.
Evaluate this Reddit post as source material for a multilingual YouTube entertainment channel.

CHANNEL PROFILE:
  Handle  : {handle}
  Language: {lang}
  Region  : {region}
  Niche   : {niche_label}

OUTSIDE PRODUCER BRIEF:
  Audience job     : {producer_context.get('audience_job')}
  Must feel like   : {producer_context.get('must_feel_like')}
  Winning bets     : {producer_context.get('winning_bets')}
  Weak-topic traps : {producer_context.get('weak_topic_traps')}

FORMAT INTENT:
  Requested format: {format_intent}
  Rules: {format_rules}

TOPIC FAMILY:
  Family : {topic_label}
  Rules  : {topic_rules}

CONTENT BET:
  Bet type        : {topic_bet.get('content_bet')}
  Why people click: {topic_bet.get('why_click')}
  Why people stay : {topic_bet.get('why_stay')}
  Shorts shape    : {topic_bet.get('shorts_shape')}
  Long-form shape : {topic_bet.get('long_shape')}
  Voice direction : {topic_bet.get('voice_direction')}
  Reject if       : {topic_bet.get('reject_if')}

CHANNEL EXCLUSIONS:
  Hard exclusions: {exclusion_text}

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
1. niche_fit       — Does this story match the exact channel promise, not just the broad language?
2. hook_strength   — Can the title + first visible screen stop a Shorts scroll in 1-2 seconds?
3. narrative_arc   — Does it have clear setup -> escalation -> payoff, or a satisfying explainable fact arc?
4. discussion_potential — Will viewers naturally argue, vote, comment, or share their own story?
5. format_fit      — Does it fit the requested format rules above?
6. translation     — Will cultural context survive translation/localization to {lang}? (10 = universal, 1 = deeply local or wordplay-only)
7. viral_potential — Based on Reddit metrics + story shape + audience fit, can this produce retention and engagement?
8. novelty         — Is it meaningfully different from common repeated Reddit tropes?
9. character_voice_fit — Would expressive/character voices make this more entertaining without sounding fake or childish?
10. slop_risk      — Risk it feels like mass-produced AI/template content (1 = specific/original, 10 = generic slop)
11. source_dependency_risk — Risk it needs an external link, image, video, screenshot, article, or comments to make sense (1 = standalone)
12. duplicate_risk — Risk this is a repeat/repost/same old trope (1 = fresh, 10 = likely duplicate)
13. legal_risk     — Risk of copyright/privacy/harmful content issues (1 = no risk, 10 = high risk)

HARD SKIP conditions:
  - SKIP posts whose title/body matches any configured channel exclusion above.
  - If the selected family is human_drama, SKIP posts that are news, product announcements, gaming/tech updates, link-only discussions, generic opinion prompts, or broad community debates without a first-person human conflict.
  - SKIP posts where the body cannot stand alone as a narrated story without opening an external link, image, video, screenshot, or article.
  - SKIP posts whose strongest appeal is only that the Reddit metrics are high.
  - SKIP posts that feel like common Reddit filler: "my partner ate my food", "roommate was annoying", "boss was rude", "what do you think?", unless there is an unusually specific twist or emotional stake.
  - SKIP posts that would become repetitive AI-slop when turned into a Reddit-card video: no distinct angle, no producer POV, no memorable moment, no reason to watch this version instead of another channel's.
  - SKIP if the story is only interesting to a narrow subreddit/fandom and cannot be made clear for the target region quickly.
  - For Shorts, SKIP if the first screen cannot carry the hook by itself.
  - For long-form, SKIP if there is not enough depth for a structured episode beyond reading the post.

PRODUCER SELECTION RULES:
  - First decide whether this is a worthwhile content bet for the audience, independent of Reddit. If it would not be worth pitching as an episode idea, SKIP.
  - Treat the Reddit post as raw material. The product is the packaged YouTube idea: hook, first screen, voice style, title/thumbnail promise, and payoff.
  - Hooks must be source-backed. Do not invent betrayals, secrets, threats, deaths, crimes, or twists that are not present in the title/body preview.
  - A stronger hook may reorder or compress existing source material, but it must preserve facts and point of view.
  - If you cannot cite an exact source quote that supports the hook/first screen, lower hook_strength and choose SKIP or REWRITE.
  - Reddit upvotes are evidence, not permission. High metrics must never override weak storytelling.
  - Prefer topics with a repeatable channel promise: viewers should understand why this channel chose it.
  - Prefer topics that can be packaged with a strong title, thumbnail text, and character voice performance.
  - Favor emotional clarity over factual complexity for Shorts.
  - Favor structure, timeline, stakes, and payoff for long-form.
  - When uncertain between weak PUBLISH and SKIP, choose SKIP.

VERDICT rules:
  PUBLISH  → niche_fit >= 7 AND hook_strength >= 7 AND viral_potential >= 7 AND format_fit >= 7 AND discussion_potential >= 6 AND novelty >= 6 AND slop_risk <= 4 AND source_dependency_risk <= 4 AND duplicate_risk <= 5 AND legal_risk <= 5
  REWRITE  → niche_fit >= 6 AND viral_potential >= 6 AND format_fit >= 6 AND slop_risk <= 5 AND legal_risk <= 6, but hook_strength is fixable with a better opening
  SKIP     → niche_fit < 6 OR viral_potential < 6 OR format_fit < 6 OR slop_risk > 5 OR source_dependency_risk > 5 OR duplicate_risk > 6 OR legal_risk > 6

Return ONLY a JSON object, no markdown:
{{
  "verdict": "PUBLISH" | "REWRITE" | "SKIP",
  "niche_fit": <int>,
  "hook_strength": <int>,
  "narrative_arc": <int>,
  "discussion_potential": <int>,
  "format_fit": <int>,
  "translation": <int>,
  "viral_potential": <int>,
  "novelty": <int>,
  "character_voice_fit": <int>,
  "slop_risk": <int>,
  "source_dependency_risk": <int>,
  "duplicate_risk": <int>,
  "legal_risk": <int>,
  "topic_family": "<best matching family>",
  "content_bet": "<moral_court|mystery|counterintuitive_fact|football_identity|internet_lore|visual_comedy|other>",
  "shorts_hook_type": "<controversy|twist|mystery|fact|challenge|identity|other>",
  "format_recommendation": "<shorts|long|both|skip>",
  "audience_job_fit": "<one sentence on whether this satisfies the outside producer brief>",
  "first_screen_promise": "<what the viewer understands from the first visible screen, or null>",
  "first_screen_text": "<source-backed first visible line/screen text, max 180 chars, or null>",
  "packaging_thesis": "<how to package this as a YouTube idea, or null>",
  "why_now": "<why this is worth publishing now, or null>",
  "shorts_cut": "<specific Shorts cut idea, or null>",
  "longform_angle": "<specific long-form expansion angle, or null>",
  "producer_angle": "<one concise angle that makes this worth producing, or null>",
  "hook_evidence": [
    {{"field": "title|body", "quote": "<exact short source quote supporting the hook>", "why_it_matters": "<why this quote supports the first screen>"}}
  ],
  "source_integrity": {{
    "can_adapt_without_inventing": <true|false>,
    "facts_not_in_source": []
  }},
  "reason": "<one sentence explaining verdict>",
  "hook_suggestion": "<source-backed rewritten opening line for Shorts, or null if not needed>"
}}
"""

    try:
        result = call_gemini_json(
            prompt=prompt,
            model=os.environ.get("AI_QUALITY_MODEL"),
            temperature=0.25,
            max_output_tokens=3200,
        )
        verdict = result.get("verdict", "PUBLISH").upper()
        if verdict not in ("PUBLISH", "REWRITE", "SKIP"):
            verdict = "PUBLISH"
        result["verdict"] = verdict
        return result
    except VectorEngineError as e:
        verdict = "PUBLISH" if AI_QUALITY_FAIL_OPEN else "SKIP"
        print(f"  [quality] Gemini error — defaulting to {verdict}: {e}")
        return {"verdict": verdict, "reason": f"API error: {e}"}
    except Exception as e:
        verdict = "PUBLISH" if AI_QUALITY_FAIL_OPEN else "SKIP"
        print(f"  [quality] Unexpected error — defaulting to {verdict}: {e}")
        return {"verdict": verdict, "reason": f"Unexpected error: {e}"}


def fetch_top_comments(reddit, post_id, subreddit, limit=3):
    """Fetch top comments for a post, excluding AutoModerator."""
    if limit <= 0:
        return []
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
        record["content_bet"] = story.get("content_bet")
        record["time_window"] = story.get("time_window")
        record["virality_score"] = story.get("virality_score")
        record["producer_score"] = story.get("producer_score")
        record["producer_rank"] = story.get("producer_rank")
        record["base_virality_score"] = story.get("base_virality_score")
        record["velocity"] = story.get("velocity")
        record["fatigue_penalty"] = story.get("fatigue_penalty")
        record["hook_evidence"] = story.get("hook_evidence")
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


def channel_topic_exclusions(channel_config: dict | None) -> list[str]:
    if not channel_config:
        return []
    values = channel_config.get("topic_exclusions") or []
    if not isinstance(values, list):
        return []
    return [
        re.sub(r"\s+", " ", str(value).casefold()).strip()
        for value in values
        if str(value or "").strip()
    ]


def matching_topic_exclusion(title: str, body: str, exclusions: list[str]) -> str | None:
    if not exclusions:
        return None
    haystack = re.sub(r"\s+", " ", f"{title or ''}\n{body or ''}".casefold())
    for exclusion in exclusions:
        if exclusion and exclusion in haystack:
            return exclusion
    return None


def build_topic_sources(
    subreddits: list[str],
    time_filter: str,
    channel_config: dict | None = None,
    topic_family: str | None = None,
) -> list[dict]:
    mix = channel_topic_mix(channel_config)
    if topic_family:
        mix = [item for item in mix if item.get("family") == topic_family]
        if not mix and topic_family in TOPIC_FAMILY_PRESETS:
            mix = [{"family": topic_family, "weight": 1.0}]

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
                     similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
                     format_intent: str | None = None,
                     producer_queue_output: str | None = "producer_queue.json"):
    """
    Search topic-family sources for the most viral post, then run a bounded AI
    quality gate (Gemini provider selected by vectorengine_client.py) to confirm channel fit, novelty, and
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
    format_intent  : str|None   - auto | shorts | long; passed to Gemini producer gate
    producer_queue_output: str|None - JSON report of all AI-scored candidates

    Returns
    -------
    dict  - story payload ready for story_data.json
    """
    reddit = get_reddit()
    history = load_history()
    max_ai_candidates = DEFAULT_MAX_AI_CANDIDATES if max_ai_candidates is None else max_ai_candidates
    format_intent = (format_intent or "auto").strip().lower()

    # ── Phase 1: collect candidates across topic families and time windows ─
    candidates = []
    seen_post_ids = set()
    seen_signatures = set()
    seen_keyword_signatures = []
    recent_records = recent_channel_records(history, channel_id)
    topic_exclusions = channel_topic_exclusions(channel_config)
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
                        excluded_term = matching_topic_exclusion(post.title, body, topic_exclusions)
                        if excluded_term:
                            print(f"    skip topic exclusion ({excluded_term}) | {post.title[:55]}")
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
    chosen_queue_entry = None
    chosen_producer_score = None
    queue_entries = []
    approved_candidates = []
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
                "format_intent": format_intent,
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
            format_intent=format_intent,
        )
        verdict = qc.get("verdict", "PUBLISH")
        print(f"   Verdict: {verdict} | "
              f"niche={qc.get('niche_fit','?')} "
              f"hook={qc.get('hook_strength','?')} "
              f"arc={qc.get('narrative_arc','?')} "
              f"discuss={qc.get('discussion_potential','?')} "
              f"format={qc.get('format_fit','?')} "
              f"translate={qc.get('translation','?')} "
              f"viral={qc.get('viral_potential','?')} "
              f"novelty={qc.get('novelty','?')} "
              f"slop={qc.get('slop_risk','?')} "
              f"source={qc.get('source_dependency_risk','?')} "
              f"dupe={qc.get('duplicate_risk','?')} "
              f"risk={qc.get('legal_risk','?')}")
        if qc.get("producer_angle"):
            print(f"   Angle  : {qc.get('producer_angle')}")
        if qc.get("packaging_thesis"):
            print(f"   Pack   : {qc.get('packaging_thesis')}")
        print(f"   Reason : {qc.get('reason', '')}")

        queue_entry = producer_queue_entry(candidate, rank + 1, qc)
        queue_entries.append(queue_entry)
        print(f"   Prod   : {queue_entry['producer_score']}")

        if verdict == "SKIP":
            print("   ⛔ Skipped by AI — trying next candidate...")
            continue

        approved_candidates.append({
            "candidate": candidate,
            "rank": rank + 1,
            "ai_result": qc,
            "producer_score": queue_entry["producer_score"],
            "queue_entry": queue_entry,
        })

    approved_candidates.sort(key=lambda item: item["producer_score"], reverse=True)
    for producer_rank, item in enumerate(approved_candidates, start=1):
        item["queue_entry"]["producer_rank"] = producer_rank

    if skip_rank and approved_candidates:
        print(f"\nVideo slot offset: skipping {skip_rank} approved candidate(s) after producer ranking.")

    if len(approved_candidates) > skip_rank:
        selected = approved_candidates[skip_rank]
        chosen_candidate = selected["candidate"]
        chosen_post = chosen_candidate["post"]
        chosen_score = chosen_candidate["score"]
        chosen_producer_score = selected["producer_score"]
        ai_result = selected["ai_result"]
        chosen_rank = selected["rank"]
        chosen_queue_entry = selected["queue_entry"]

    write_producer_queue(
        producer_queue_output,
        channel_id=channel_id,
        format_intent=format_intent,
        candidates_total=len(candidates),
        ai_budget=len(ai_candidates),
        skip_rank=skip_rank,
        entries=sorted(queue_entries, key=lambda item: item.get("producer_score") or 0, reverse=True),
        chosen_entry=chosen_queue_entry,
    )

    if not chosen_post:
        print("\n❌ No candidate passed within the AI quality budget.")
        return None

    print(f"\n✅ Story approved (producer_score={chosen_producer_score}, virality={chosen_score}, verdict={ai_result.get('verdict')}):")
    print(f"   r/{chosen_post.subreddit} — {chosen_post.title[:70]}")
    print(f"   {format_count(chosen_post.score)} upvotes | "
          f"{format_count(chosen_post.num_comments)} comments")
    print(f"   topic={chosen_candidate['topic']['family']} | window=top/{chosen_candidate['time_window']}")
    if chosen_queue_entry and chosen_queue_entry.get("first_screen_text"):
        print(f"   first screen: {chosen_queue_entry.get('first_screen_text')}")

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
        "producer_rank": chosen_queue_entry.get("producer_rank") if chosen_queue_entry else None,
        "producer_score": chosen_producer_score,
        "candidate_pool_size": len(candidates),
        "ai_candidate_budget": len(ai_candidates),
        "ai_quality": ai_result,
        "producer_queue_entry": chosen_queue_entry,
        "format_intent": format_intent,
        "format_recommendation": ai_result.get("format_recommendation"),
        "content_bet": ai_result.get("content_bet"),
        "audience_job_fit": ai_result.get("audience_job_fit"),
        "first_screen_promise": ai_result.get("first_screen_promise"),
        "first_screen_text": ai_result.get("first_screen_text"),
        "packaging_thesis": ai_result.get("packaging_thesis"),
        "why_now": ai_result.get("why_now"),
        "shorts_cut": ai_result.get("shorts_cut"),
        "longform_angle": ai_result.get("longform_angle"),
        "producer_angle": ai_result.get("producer_angle"),
        "hook_evidence": hook_evidence_items(ai_result),
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
    parser.add_argument("--comment-limit", type=int, default=3,
                        help="Number of Reddit comments to fetch for the story (default: 3)")
    parser.add_argument("--max-body-chars", type=int, default=None,
                        help="Trim story body to this many characters after selection, for Shorts tests.")
    parser.add_argument("--format-intent", default=None,
                        help="Optional content format label stored in story metadata, e.g. shorts or long.")
    parser.add_argument("--producer-queue-output", default="producer_queue.json",
                        help="Write all AI-scored candidates and producer ranking to this JSON file.")
    parser.add_argument("--no-producer-queue", action="store_true",
                        help="Do not write producer_queue.json.")
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
        comment_limit=args.comment_limit,
        topic_family=args.topic_family,
        similarity_threshold=args.similarity_threshold,
        format_intent=args.format_intent,
        producer_queue_output=None if args.no_producer_queue else args.producer_queue_output,
    )

    if story:
        story = apply_story_length_limits(
            story,
            max_body_chars=args.max_body_chars,
            max_comments=args.comment_limit,
            format_intent=args.format_intent,
        )
        output_path = os.path.join(os.path.dirname(__file__), args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(story, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Saved → {output_path}")
        save_history(story["post_id"], channel_key, story)
    else:
        print("\n❌ No story found. Try a different subreddit or time filter.")
        sys.exit(1)
