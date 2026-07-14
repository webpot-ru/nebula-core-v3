import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scraper
import acc1_story_strategy
from scripts import build_acc1_greenlight_template as greenlight_template
from scripts import review_reddit_topics


class Acc1GreenlightTemplateTests(unittest.TestCase):
    @staticmethod
    def _entry(post_id: str = "candidate-1", *, link_dependent: bool = False) -> dict:
        sentence = "My husband argued with my family and our relationship changed forever. "
        body = " ".join([
            *(
                f"{sentence} Detail{index} changed consequence{index} before event{index} "
                "and the next decision."
                for index in range(180)
            ),
            "Finally, we broke up and I blocked him.",
        ])
        return {
            "post_id": post_id,
            "title": "My husband and my family forced me to choose",
            "subreddit": "r/relationship_advice",
            "url": f"https://reddit.com/r/relationship_advice/comments/{post_id}/story/",
            "source_body": body,
            "source_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "source_word_count": len(review_reddit_topics.WORD_RE.findall(body)),
            "source_has_url": False,
            "source_has_markdown_link": link_dependent,
            "source_has_markdown_image": False,
            "topic_family": "human_drama",
            "local_score": 80,
        }

    def _queue(self, entries: list[dict] | None = None) -> dict:
        resolved_entries = entries if entries is not None else [self._entry()]
        return {
            "channel_id": "acc1",
            "format_intent": "saga",
            "source_plan": {
                "pilot_id": "pilot_01",
                "format": "SAGA",
                "pillar": "relationships_family",
                "topic_family": "human_drama",
                "subreddits": ["relationship_advice", "AmItheAsshole"],
                "format_intent": "saga",
                "target_duration_minutes": [18, 30],
                "source_word_count": [2340, 3900],
                "words_per_minute": 130,
            },
            "selected_post_id": resolved_entries[0]["post_id"] if resolved_entries else None,
            "entries": resolved_entries,
        }

    @staticmethod
    def _review(queue: dict) -> dict:
        return review_reddit_topics.build_review(queue, 3)

    def test_template_is_deterministic_and_preserves_queue_selection(self):
        queue = self._queue()
        review = self._review(queue)
        first = greenlight_template.build_template(queue, review)
        second = greenlight_template.build_template(queue, review)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "DRAFT_BLOCKED")
        self.assertEqual(first["pilot_id"], "pilot_01")
        self.assertEqual(first["source"]["post_id"], queue["selected_post_id"])
        self.assertEqual(first["selection_contract"]["mode"], "queue_selected_post_id")
        self.assertFalse(first["selection_contract"]["preliminary_story_superseded"])
        self.assertEqual(first["artifact_bindings"]["source_sha256"], review["source_sha256"])
        self.assertEqual(first["artifact_bindings"]["review_sha256"], review["review_sha256"])

    def test_numeric_tokens_keep_scraper_review_and_greenlight_counts_aligned(self):
        entry = self._entry()
        entry["source_body"] += " In 2026 I paid 350 dollars in 3 installments. Finally, it was settled."
        entry["source_body_sha256"] = hashlib.sha256(
            entry["source_body"].encode("utf-8")
        ).hexdigest()
        entry["source_word_count"] = scraper.source_word_count(entry["source_body"])
        self.assertEqual(
            entry["source_word_count"],
            len(review_reddit_topics.WORD_RE.findall(entry["source_body"])),
        )
        self.assertEqual(
            entry["source_word_count"],
            len(acc1_story_strategy.WORD_RE.findall(entry["source_body"])),
        )
        queue = self._queue([entry])
        review = self._review(queue)
        payload = greenlight_template.build_template(queue, review)
        self.assertEqual(payload["source"]["source_word_count"], entry["source_word_count"])

    def test_tampered_queue_or_review_fails_closed(self):
        queue = self._queue()
        review = self._review(queue)
        tampered_queue = copy.deepcopy(queue)
        tampered_queue["entries"][0]["title"] = "tampered title"
        with self.assertRaisesRegex(greenlight_template.GreenlightTemplateError, "source_sha256"):
            greenlight_template.build_template(tampered_queue, review)

        tampered_review = copy.deepcopy(review)
        tampered_review["top_topics"][0]["source_word_count"] += 1
        with self.assertRaisesRegex(greenlight_template.GreenlightTemplateError, "review_sha256"):
            greenlight_template.build_template(queue, tampered_review)

    def test_ineligible_source_cannot_create_template(self):
        queue = self._queue([self._entry(link_dependent=True)])
        review = self._review(queue)
        self.assertEqual(review["top_topics"], [])
        with self.assertRaisesRegex(greenlight_template.GreenlightTemplateError, "no candidate"):
            greenlight_template.build_template(queue, review)

    def test_template_never_claims_creative_or_publication_pass(self):
        queue = self._queue()
        payload = greenlight_template.build_template(queue, self._review(queue))
        self.assertFalse(payload["production_authorized"])
        self.assertFalse(payload["publication_authorized"])
        self.assertEqual(payload["packaging_options"], [])
        self.assertEqual(payload["cold_open"], {})
        self.assertEqual(payload["story_beats"], [])
        self.assertEqual(payload["originality_plan"], {})
        self.assertEqual(payload["scores"], {field: 0 for field in greenlight_template.SCORE_FIELDS})
        self.assertTrue(payload["draft_blockers"])
        self.assertTrue(payload["source"]["runtime_fit"])
        self.assertTrue(payload["source"]["payoff_complete"])
        self.assertFalse(payload["source"]["depends_on_screenshot_or_link"])

    def test_explicit_post_id_must_be_an_eligible_top_topic(self):
        entries = [self._entry("candidate-1"), self._entry("candidate-2")]
        entries[1]["local_score"] = 95
        queue = self._queue(entries)
        review = self._review(queue)
        payload = greenlight_template.build_template(queue, review, post_id="candidate-2")
        self.assertEqual(payload["source"]["post_id"], "candidate-2")
        self.assertEqual(payload["selection_contract"]["mode"], "explicit_post_id")
        self.assertTrue(payload["selection_contract"]["preliminary_story_superseded"])
        with self.assertRaisesRegex(greenlight_template.GreenlightTemplateError, "exactly one"):
            greenlight_template.build_template(queue, review, post_id="not-reviewed")

    def test_review_rerank_cannot_silently_replace_queue_story(self):
        queue = self._queue([self._entry("candidate-1"), self._entry("candidate-2")])
        review = self._review(queue)
        review["top_topics"].reverse()
        review_without_hash = dict(review)
        review_without_hash.pop("review_sha256")
        review["review_sha256"] = greenlight_template.canonical_content_hash(review_without_hash)

        payload = greenlight_template.build_template(queue, review)

        self.assertEqual(review["top_topics"][0]["post_id"], "candidate-2")
        self.assertEqual(payload["source"]["post_id"], "candidate-1")
        self.assertEqual(payload["selection_contract"]["review_top_post_id"], "candidate-2")
        self.assertFalse(payload["selection_contract"]["preliminary_story_superseded"])

    def test_missing_or_ineligible_queue_selection_fails_closed(self):
        queue = self._queue()
        review = self._review(queue)
        queue_without_selection = copy.deepcopy(queue)
        queue_without_selection.pop("selected_post_id")
        review_without_selection = self._review(queue_without_selection)
        with self.assertRaisesRegex(greenlight_template.GreenlightTemplateError, "selected_post_id is required"):
            greenlight_template.build_template(queue_without_selection, review_without_selection)

        queue["selected_post_id"] = "not-reviewed"
        review = self._review(queue)
        with self.assertRaisesRegex(greenlight_template.GreenlightTemplateError, "eligible topic-review"):
            greenlight_template.build_template(queue, review)

    def test_cli_writes_the_same_fail_closed_schema(self):
        queue = self._queue()
        review = self._review(queue)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            queue_path = root / "queue.json"
            review_path = root / "review.json"
            output_path = root / "greenlight.json"
            queue_path.write_text(json.dumps(queue), encoding="utf-8")
            review_path.write_text(json.dumps(review), encoding="utf-8")
            argv = [
                "build_acc1_greenlight_template.py",
                "--queue", str(queue_path),
                "--review", str(review_path),
                "--output", str(output_path),
            ]
            with mock.patch("sys.argv", argv):
                self.assertEqual(greenlight_template.main(), 0)
            written = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(written, greenlight_template.build_template(queue, review))
        self.assertEqual(written["status"], "DRAFT_BLOCKED")
        self.assertFalse(written["publication_authorized"])


if __name__ == "__main__":
    unittest.main()
