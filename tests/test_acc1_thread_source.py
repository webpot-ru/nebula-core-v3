import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import acc1_thread_collector
import acc1_thread_source


PROMPT_ID = "ask123"


def long_body(index: int, words: int = 120) -> str:
    details = " ".join(f"account{index}detail{word}" for word in range(words))
    return f"Full response {index} begins here.\n\n{details}\n\nFull response {index} ends here."


def alpha_token(value: int) -> str:
    result = ""
    number = value + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("a") + remainder) + result
    return result


class FakeComments(list):
    def replace_more(self, *args, **kwargs):
        raise AssertionError("bounded THREAD source must never call replace_more")


class FakeComment:
    def __init__(
        self,
        index: int,
        *,
        prompt_id: str = PROMPT_ID,
        score: int | None = None,
        body: str | None = None,
        author: str | None = None,
        parent_id: str | None = None,
        depth: int | None = 0,
        **flags,
    ):
        self.id = f"comment{index:02d}"
        self.author = f"author_{index:02d}" if author is None else author
        self.score = 1000 - index if score is None else score
        self.body = long_body(index) if body is None else body
        self.permalink = (
            f"/r/AskReddit/comments/{prompt_id}/question/{self.id}/"
        )
        self.parent_id = f"t3_{prompt_id}" if parent_id is None else parent_id
        self.depth = depth
        self.removed_by_category = None
        for key, value in flags.items():
            setattr(self, key, value)


class FakeSubmission:
    def __init__(
        self,
        prompt_id: str,
        comments,
        *,
        score: int = 5000,
        num_comments: int | None = None,
        subreddit: str = "AskReddit",
        title: str | None = None,
    ):
        self.id = prompt_id
        self.title = title or f"What happened in prompt {prompt_id}?"
        self.selftext = "Share the complete experience and what happened afterward."
        self.author = "prompt_author"
        self.score = score
        self.num_comments = len(comments) if num_comments is None else num_comments
        self.permalink = f"/r/{subreddit}/comments/{prompt_id}/question/"
        self.subreddit = SimpleNamespace(display_name=subreddit)
        self.comments = FakeComments(comments)
        self.stickied = False
        self.is_self = True
        self.comment_sort = None
        self.comment_limit = None


class FakeSubreddit:
    def __init__(self, submissions):
        self.submissions = list(submissions)
        self.calls = []

    def top(self, *, time_filter, limit):
        self.calls.append({"time_filter": time_filter, "limit": limit})
        return list(self.submissions[:limit])

    def search(self, query, *, sort, time_filter, limit):
        self.calls.append({
            "query": query,
            "sort": sort,
            "time_filter": time_filter,
            "limit": limit,
        })
        return list(self.submissions[:limit])


class FakeReddit:
    def __init__(self, submissions, subreddit_submissions=None):
        self.submissions = {item.id: item for item in submissions}
        self.fake_subreddit = FakeSubreddit(
            subreddit_submissions if subreddit_submissions is not None else submissions
        )
        self.submission_calls = []
        self.subreddit_calls = []

    def submission(self, *, id):
        self.submission_calls.append(id)
        return self.submissions[id]

    def subreddit(self, name):
        self.subreddit_calls.append(name)
        return self.fake_subreddit


def submission_with_comments(
    prompt_id: str = PROMPT_ID,
    count: int = 8,
    *,
    score: int = 5000,
    num_comments: int | None = None,
):
    return FakeSubmission(
        prompt_id,
        [FakeComment(index, prompt_id=prompt_id) for index in range(count)],
        score=score,
        num_comments=num_comments,
    )


class Acc1ThreadSourceTests(unittest.TestCase):
    def test_bounded_discovery_can_return_five_review_candidates(self):
        submissions = []
        role_openings = (
            "I remember when this experience began, and after the incident I stayed until it ended.",
            "In my profession this experience happens for a reason, and at work I followed the standard procedure.",
            "However, my experience ended differently; unlike the first assumption, the real cause became clear.",
            "I realized this experience changed my view, and since then I understand why the ending mattered.",
        )
        for prompt_index in range(5):
            prompt_id = f"prompt{prompt_index}"
            comments = [
                FakeComment(
                    response_index,
                    prompt_id=prompt_id,
                    body=(
                        f"{role_openings[response_index % len(role_openings)]} "
                        + " ".join(
                            f"detail {alpha_token(prompt_index * 300 + response_index * 50 + word)} gradually changed the final outcome"
                            for word in range(40)
                        )
                        + f" Eventually I saw the complete outcome of experience {response_index}."
                    ),
                )
                for response_index in range(8)
            ]
            submissions.append(FakeSubmission(
                prompt_id,
                comments,
                score=9000 - prompt_index,
            ))
        results = acc1_thread_source.collect_thread_source_candidates(
            FakeReddit(submissions),
            candidate_limit=5,
            finalist_limit=5,
            response_scan_limit=8,
            max_responses=8,
            require_episode_runtime=True,
        )
        self.assertEqual(len(results), 5)
        self.assertEqual(
            [manifest["prompt"]["id"] for _snapshot, manifest in results],
            [f"prompt{index}" for index in range(5)],
        )

    def test_exact_prompt_read_preserves_full_comments_and_provenance(self):
        submission = submission_with_comments(count=8)
        reddit = FakeReddit([submission])

        snapshot, manifest = acc1_thread_source.collect_thread_source(
            reddit,
            prompt_id=PROMPT_ID,
            response_scan_limit=8,
            max_responses=8,
        )

        self.assertEqual(reddit.submission_calls, [PROMPT_ID])
        self.assertEqual(reddit.subreddit_calls, [])
        self.assertEqual(submission.comment_sort, "top")
        self.assertEqual(submission.comment_limit, 8)
        self.assertEqual(len(snapshot["responses"]), 8)
        first = next(item for item in snapshot["responses"] if item["id"] == "comment00")
        self.assertGreater(len(first["body"]), 400)
        self.assertEqual(first["body"], long_body(0))
        self.assertEqual(first["author"], "author_00")
        self.assertEqual(first["score"], 1000)
        self.assertEqual(first["parent_id"], f"t3_{PROMPT_ID}")
        self.assertEqual(first["depth"], 0)
        self.assertTrue(first["source_url"].endswith("/comment00/"))
        self.assertFalse(first["is_deleted"])
        self.assertFalse(first["is_removed"])
        self.assertFalse(first["is_truncated"])
        self.assertFalse(first["depends_on_external_context"])
        self.assertEqual(manifest["prompt"]["id"], PROMPT_ID)
        self.assertEqual(manifest["response_count"], 8)
        self.assertTrue(acc1_thread_collector.verify_manifest(manifest))

    def test_discovery_is_bounded_ranked_and_falls_back_to_next_valid_prompt(self):
        high_but_insufficient = submission_with_comments(
            "high111", count=7, score=9000, num_comments=100
        )
        valid = submission_with_comments("valid22", count=8, score=8000, num_comments=80)
        reddit = FakeReddit(
            [high_but_insufficient, valid],
            subreddit_submissions=[valid, high_but_insufficient],
        )

        snapshot, manifest = acc1_thread_source.collect_thread_source(
            reddit,
            candidate_limit=2,
            response_scan_limit=8,
            max_responses=8,
            time_filter="week",
        )

        self.assertEqual(reddit.fake_subreddit.calls, [{"time_filter": "week", "limit": 2}])
        self.assertEqual(high_but_insufficient.comment_limit, 8)
        self.assertEqual(valid.comment_limit, 8)
        self.assertEqual(snapshot["prompt"]["id"], "valid22")
        self.assertEqual(manifest["prompt"]["id"], "valid22")

    def test_search_query_is_exact_and_preserved_in_snapshot(self):
        valid = submission_with_comments("search22", count=8, score=8000, num_comments=80)
        reddit = FakeReddit([valid])

        snapshot, manifest = acc1_thread_source.collect_thread_source(
            reddit,
            search_query='("job" OR "profession")',
            candidate_limit=1,
            response_scan_limit=8,
            max_responses=8,
            time_filter="year",
        )

        self.assertEqual(
            reddit.fake_subreddit.calls,
            [{
                "query": '("job" OR "profession")',
                "sort": "top",
                "time_filter": "year",
                "limit": 1,
            }],
        )
        self.assertEqual(snapshot["query"]["mode"], "subreddit_search")
        self.assertEqual(snapshot["query"]["search_query"], '("job" OR "profession")')
        self.assertEqual(manifest["prompt"]["id"], "search22")

    def test_published_prompt_ids_are_skipped_before_comment_collection(self):
        published = submission_with_comments("used111", count=8, score=9000)
        fresh = submission_with_comments("fresh22", count=8, score=8000)
        reddit = FakeReddit(
            [published, fresh], subreddit_submissions=[published, fresh]
        )
        snapshot, manifest = acc1_thread_source.collect_thread_source(
            reddit,
            candidate_limit=2,
            response_scan_limit=8,
            max_responses=8,
            excluded_prompt_ids={"used111"},
        )
        self.assertEqual(snapshot["prompt"]["id"], "fresh22")
        self.assertEqual(manifest["prompt"]["id"], "fresh22")
        self.assertIsNone(published.comment_limit)
        self.assertEqual(snapshot["query"]["excluded_prompt_id_count"], 1)

    def test_response_scan_limit_bounds_snapshot_and_selection(self):
        submission = submission_with_comments(count=20)
        reddit = FakeReddit([submission])

        snapshot, manifest = acc1_thread_source.collect_thread_source(
            reddit,
            prompt_id=PROMPT_ID,
            response_scan_limit=10,
            max_responses=8,
        )

        self.assertEqual(len(snapshot["responses"]), 10)
        self.assertEqual(manifest["response_count"], 8)
        self.assertEqual(manifest["selection"]["unselected_eligible_count"], 2)

    def test_deleted_removed_truncated_and_dependency_flags_survive_snapshot(self):
        comments = [FakeComment(index) for index in range(8)]
        deleted = FakeComment(8, author=None, body="[deleted]", score=-1)
        deleted.author = None
        removed = FakeComment(9, body="[removed]", score=-2)
        removed.removed_by_category = "moderator"
        truncated = FakeComment(10, score=-3, is_truncated=True)
        dependent = FakeComment(11, score=-4, depends_on_screenshot=True)
        submission = FakeSubmission(
            PROMPT_ID,
            comments + [deleted, removed, truncated, dependent],
        )
        reddit = FakeReddit([submission])

        snapshot, manifest = acc1_thread_source.collect_thread_source(
            reddit,
            prompt_id=PROMPT_ID,
            response_scan_limit=12,
            max_responses=8,
        )

        indexed = {item["id"]: item for item in snapshot["responses"]}
        self.assertTrue(indexed["comment08"]["is_deleted"])
        self.assertTrue(indexed["comment09"]["is_removed"])
        self.assertEqual(indexed["comment09"]["removed_by_category"], "moderator")
        self.assertTrue(indexed["comment10"]["is_truncated"])
        self.assertTrue(indexed["comment11"]["depends_on_screenshot"])
        self.assertTrue(indexed["comment11"]["depends_on_external_context"])
        self.assertEqual(manifest["response_count"], 8)
        self.assertEqual(manifest["rejection_reason_counts"]["deleted_or_removed_body"], 2)
        self.assertEqual(manifest["rejection_reason_counts"]["truncated_body"], 1)
        self.assertEqual(manifest["rejection_reason_counts"]["external_context_dependency"], 1)

    def test_snapshot_and_manifest_are_deterministic_when_comment_order_changes(self):
        comments = [FakeComment(index) for index in range(9)]
        forward = FakeSubmission(PROMPT_ID, comments)
        reverse = FakeSubmission(PROMPT_ID, list(reversed(copy.deepcopy(comments))))

        first_snapshot, first_manifest = acc1_thread_source.collect_thread_source(
            FakeReddit([forward]),
            prompt_id=PROMPT_ID,
            response_scan_limit=9,
            max_responses=8,
        )
        second_snapshot, second_manifest = acc1_thread_source.collect_thread_source(
            FakeReddit([reverse]),
            prompt_id=PROMPT_ID,
            response_scan_limit=9,
            max_responses=8,
        )

        self.assertEqual(first_snapshot, second_snapshot)
        self.assertEqual(first_manifest, second_manifest)

    def test_fails_closed_when_bounded_comments_cannot_supply_eight_valid_responses(self):
        submission = submission_with_comments(count=7, num_comments=100)
        reddit = FakeReddit([submission])

        with self.assertRaisesRegex(acc1_thread_source.ThreadSourceError, "no bounded prompt"):
            acc1_thread_source.collect_thread_source(
                reddit,
                prompt_id=PROMPT_ID,
                response_scan_limit=8,
                max_responses=8,
            )

    def test_cli_refuses_reddit_client_without_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "snapshot.json"
            manifest_path = Path(temp_dir) / "manifest.json"
            stderr = io.StringIO()
            with patch("scraper.get_reddit") as get_reddit, redirect_stderr(stderr):
                status = acc1_thread_source.main(
                    [
                        "--snapshot-output",
                        str(snapshot_path),
                        "--manifest-output",
                        str(manifest_path),
                    ]
                )

            self.assertEqual(status, 2)
            get_reddit.assert_not_called()
            self.assertIn("--confirm-reddit-read", stderr.getvalue())
            self.assertFalse(snapshot_path.exists())
            self.assertFalse(manifest_path.exists())

    def test_confirmed_cli_uses_scraper_client_and_writes_both_artifacts(self):
        submission = submission_with_comments(count=8)
        reddit = FakeReddit([submission])
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "snapshot.json"
            manifest_path = Path(temp_dir) / "manifest.json"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch("scraper.get_reddit", return_value=reddit) as get_reddit,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                status = acc1_thread_source.main(
                    [
                        "--confirm-reddit-read",
                        "--prompt-id",
                        PROMPT_ID,
                        "--response-scan-limit",
                        "8",
                        "--max-responses",
                        "8",
                        "--snapshot-output",
                        str(snapshot_path),
                        "--manifest-output",
                        str(manifest_path),
                    ]
                )

            self.assertEqual(status, 0, stderr.getvalue())
            get_reddit.assert_called_once_with()
            report = json.loads(stdout.getvalue())
            stored_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            stored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "READY")
            self.assertEqual(stored_snapshot["prompt"]["id"], PROMPT_ID)
            self.assertTrue(acc1_thread_collector.verify_manifest(stored_manifest))


if __name__ == "__main__":
    unittest.main()
