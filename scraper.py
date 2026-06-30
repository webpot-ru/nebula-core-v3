import json
import random
import sys
import os

# ─────────────────────────────────────────────
#  PRAW-based Reddit scraper with virality scoring
#  Requires env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
#                     REDDIT_USERNAME, REDDIT_PASSWORD
# ─────────────────────────────────────────────

def get_reddit():
    """Authenticate with Reddit via PRAW (script app, read-only for public data).

    Reddit 2026 requires username even for script-type apps.
    user_agent must follow: platform:app_id:version (by u/username)
    """
    try:
        import praw
    except ImportError:
        os.system("pip3 install praw -q")
        import praw

    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ.get("REDDIT_USERNAME", "Complex_Lack4476"),
        password=os.environ.get("REDDIT_PASSWORD", ""),
        user_agent="macos:ChonkerTalksBot:v1.0 (by /u/Complex_Lack4476)"
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
                     min_body_length=300, comment_limit=3, channel_id="default"):
    """
    Search multiple subreddits for the most viral post.

    Parameters
    ----------
    subreddits     : list[str]  - subreddit names (without r/)
    time_filter    : str        - 'day' | 'week' | 'month' | 'year'
    min_upvotes    : int        - minimum upvote threshold
    min_body_length: int        - minimum post body length in characters
    comment_limit  : int        - number of top comments to fetch
    channel_id     : str        - active channel index for duplicate protection

    Returns
    -------
    dict  - story payload ready for story_data.json
    """
    reddit = get_reddit()
    best_post = None
    best_score = -1
    history = load_history()

    for sub_name in subreddits:
        print(f"  Scanning r/{sub_name} (top/{time_filter})...")
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.top(time_filter=time_filter, limit=30):
                # Hard filters
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

                if score > best_score:
                    best_score = score
                    best_post = post

        except Exception as e:
            print(f"  Error scanning r/{sub_name}: {e}")
            continue

    if not best_post:
        print("No suitable story found.")
        return None

    print(f"\n✅ Best story selected (virality={best_score}):")
    print(f"   r/{best_post.subreddit} — {best_post.title[:70]}")
    print(f"   {format_count(best_post.score)} upvotes | "
          f"{format_count(best_post.num_comments)} comments")

    comments = fetch_top_comments(
        reddit, best_post.id, str(best_post.subreddit), limit=comment_limit
    )

    return {
        "subreddit": f"r/{best_post.subreddit}",
        "title": best_post.title,
        "author": f"u/{best_post.author}" if best_post.author else "u/deleted",
        "body": best_post.selftext,
        "upvotes": format_count(best_post.score),
        "comments_count": format_count(best_post.num_comments),
        "virality_score": best_score,
        "url": f"https://reddit.com{best_post.permalink}",
        "post_id": best_post.id,
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
    story = fetch_best_story(
        subreddits=subreddits,
        time_filter=args.time,
        min_upvotes=args.min_upvotes,
        channel_id=channel_key
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
