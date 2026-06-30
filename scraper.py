import json
import random
import sys
import os
import re

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


def ai_quality_check(post_title: str, post_body: str, channel: dict) -> dict:
    """
    Send the story to Gemini via VectorEngine for a structured quality assessment.

    Returns a dict with keys:
        verdict       : "PUBLISH" | "REWRITE" | "SKIP"
        niche_fit     : int 1-10
        hook_strength : int 1-10
        narrative_arc : int 1-10
        translation   : int 1-10
        legal_risk    : int 1-10  (1=safe, 10=very risky)
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
        return {"verdict": "PUBLISH", "reason": "VectorEngine not available."}

    niche_label = channel.get("niche_label", "General entertainment")
    lang        = channel.get("lang", "en")
    handle      = channel.get("handle", "unknown")
    region      = channel.get("region", "unknown")

    # Truncate body to keep prompt within token limits
    body_preview = (post_body or "")[:800]

    prompt = f"""
You are a YouTube content strategist. Evaluate this Reddit story for a specific channel.

CHANNEL PROFILE:
  Handle  : {handle}
  Language: {lang}
  Region  : {region}
  Niche   : {niche_label}

STORY:
  Title: {post_title}
  Body (first 800 chars): {body_preview}

SCORE each dimension from 1 (very poor) to 10 (excellent):
1. niche_fit       — Does this story match the channel niche perfectly?
2. hook_strength   — Is the first sentence strong enough to stop a Shorts scroll?
3. narrative_arc   — Does it have a clear conflict → escalation → resolution?
4. translation     — Will cultural context survive translation to {lang}? (10 = universal, 1 = deeply US-specific)
5. legal_risk      — Risk of copyright/privacy/harmful content issues (1 = no risk, 10 = high risk)

VERDICT rules:
  PUBLISH  → niche_fit >= 6 AND hook_strength >= 6 AND legal_risk <= 5
  REWRITE  → niche_fit >= 5 AND hook_strength < 6 (good story, weak hook; suggest a new hook)
  SKIP     → niche_fit < 5 OR legal_risk > 7

Return ONLY a JSON object, no markdown:
{{
  "verdict": "PUBLISH" | "REWRITE" | "SKIP",
  "niche_fit": <int>,
  "hook_strength": <int>,
  "narrative_arc": <int>,
  "translation": <int>,
  "legal_risk": <int>,
  "reason": "<one sentence explaining verdict>",
  "hook_suggestion": "<rewritten opening line for Shorts, or null if PUBLISH/SKIP>"
}}
"""

    try:
        result = call_gemini_json(prompt=prompt, temperature=0.3, max_output_tokens=600)
        verdict = result.get("verdict", "PUBLISH").upper()
        if verdict not in ("PUBLISH", "REWRITE", "SKIP"):
            verdict = "PUBLISH"
        result["verdict"] = verdict
        return result
    except VectorEngineError as e:
        print(f"  [quality] VectorEngine error — defaulting to PUBLISH: {e}")
        return {"verdict": "PUBLISH", "reason": f"API error: {e}"}
    except Exception as e:
        print(f"  [quality] Unexpected error — defaulting to PUBLISH: {e}")
        return {"verdict": "PUBLISH", "reason": f"Unexpected error: {e}"}


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


def save_history(post_id: str, channel_id: str) -> None:
    history = load_history()
    if post_id not in history:
        history[post_id] = []
    if channel_id not in history[post_id]:
        history[post_id].append(channel_id)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"  Saved post {post_id} to history for channel {channel_id}")
    except Exception as e:
        print(f"  Warning: could not save history: {e}")


def fetch_best_story(subreddits, time_filter="week", min_upvotes=1000,
                     min_body_length=300, comment_limit=3, channel_id="default",
                     channel_config=None, skip_rank=0):
    """
    Search multiple subreddits for the most viral post, then run an AI quality
    gate (Gemini via VectorEngine) to confirm the story fits the channel niche.

    Parameters
    ----------
    subreddits     : list[str]  - subreddit names (without r/)
    time_filter    : str        - 'day' | 'week' | 'month' | 'year'
    min_upvotes    : int        - minimum upvote threshold
    min_body_length: int        - minimum post body length in characters
    comment_limit  : int        - number of top comments to fetch
    channel_id     : str        - active channel index for duplicate protection
    channel_config : dict|None  - full channel dict from channels.json (for AI check)
    skip_rank      : int        - skip the top-N AI-approved candidates (for multi-slot daily publishing)

    Returns
    -------
    dict  - story payload ready for story_data.json
    """
    reddit = get_reddit()
    history = load_history()

    # ── Phase 1: collect ALL candidates, sorted by virality score ──────────
    candidates = []  # list of (score, post)

    for sub_name in subreddits:
        print(f"  Scanning r/{sub_name} (top/{time_filter})...")
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.top(time_filter=time_filter, limit=30):
                if post.stickied:
                    continue
                if post.id in history and channel_id in history[post.id]:
                    continue
                if post.score < min_upvotes:
                    continue
                body = post.selftext or ""
                if len(body) < min_body_length:
                    continue
                if body in ("[removed]", "[deleted]"):
                    continue

                score = virality_score(post)
                print(f"    [{score:3d}] {post.score:>6} ups | "
                      f"{post.num_comments:>5} comments | "
                      f"{post.title[:55]}")
                candidates.append((score, post))

        except Exception as e:
            print(f"  Error scanning r/{sub_name}: {e}")
            continue

    if not candidates:
        print("No suitable story found.")
        return None

    # Sort descending by virality score; try best candidate first
    candidates.sort(key=lambda x: x[0], reverse=True)

    # ── Phase 2: AI quality gate — iterate until PUBLISH or REWRITE ────────
    chosen_post  = None
    chosen_score = -1
    ai_result    = {}
    approved_count = 0   # counts how many candidates passed AI check

    for rank, (score, post) in enumerate(candidates):
        print(f"\n🤖 [AI quality check] #{rank+1} candidate: {post.title[:60]}")
        qc = ai_quality_check(
            post_title=post.title,
            post_body=post.selftext or "",
            channel=channel_config or {}
        )
        verdict = qc.get("verdict", "PUBLISH")
        print(f"   Verdict: {verdict} | "
              f"niche={qc.get('niche_fit','?')} "
              f"hook={qc.get('hook_strength','?')} "
              f"arc={qc.get('narrative_arc','?')} "
              f"translate={qc.get('translation','?')} "
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
        break

    if not chosen_post:
        print("\n❌ All candidates were rejected by AI quality check.")
        return None

    print(f"\n✅ Story approved (virality={chosen_score}, verdict={ai_result.get('verdict')}):")
    print(f"   r/{chosen_post.subreddit} — {chosen_post.title[:70]}")
    print(f"   {format_count(chosen_post.score)} upvotes | "
          f"{format_count(chosen_post.num_comments)} comments")

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
#    python3 scraper.py --channel acc4 --time month
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ChonkerTalks Reddit Scraper")
    parser.add_argument("subreddit", nargs="?", default=None,
                        help="Subreddit name (overrides channels.json)")
    parser.add_argument("--channel", "-c", default=None,
                        help="Channel ID from channels.json (e.g. acc1, acc4)")
    parser.add_argument("--time", "-t", default="week",
                        choices=["day", "week", "month", "year"],
                        help="Time filter for top posts (default: week)")
    parser.add_argument("--min-upvotes", "-u", type=int, default=1000,
                        help="Minimum upvotes threshold (default: 1000)")
    parser.add_argument("--output", "-o", default="story_data.json",
                        help="Output JSON file (default: story_data.json)")
    parser.add_argument("--video-slot", "-s", type=int, default=1,
                        help="Which video slot of the day (1=first/morning, 2=second/evening). "
                             "Slot N skips the top N-1 AI-approved candidates so each slot "
                             "gets a unique story. (default: 1)")
    args = parser.parse_args()

    # Determine subreddits to scan
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

    print(f"Time filter: top/{args.time} | Min upvotes: {args.min_upvotes}\n")

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
        skip_rank=skip_rank
    )

    if story:
        output_path = os.path.join(os.path.dirname(__file__), args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(story, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Saved → {output_path}")
        save_history(story["post_id"], channel_key)
    else:
        print("\n❌ No story found. Try a different subreddit or time filter.")
        sys.exit(1)
