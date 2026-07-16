import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.acc1_resume_lock import (
    FILENAME,
    ResumeLockError,
    build_resume_lease,
    canonical_hash,
    scan_existing,
    validate_resume_lease,
)
from tests.test_acc1_spend_lock import HEAD_SHA, REPOSITORY, valid_lease


def parent_evidence(run_id=101):
    lease = valid_lease(run_id=run_id)
    topic_input = {
        "daily_plan_sha256": lease["source_bindings"]["daily_plan_sha256"],
        "candidates": [{"candidate_id": "candidate-0"}],
    }
    producer = {
        "version": 1,
        "daily_plan_sha256": topic_input["daily_plan_sha256"],
        "results": [{"status": "PASS"}],
    }
    critic = {
        "version": 1,
        "daily_plan_sha256": topic_input["daily_plan_sha256"],
        "results": [{"status": "PASS"}],
    }
    journal = {
        "version": 1,
        "provider": "openai",
        "cap": 64,
        "token_cap": 1_000_000,
        "usage_totals": {
            "input_tokens": 10,
            "cached_input_tokens": 0,
            "output_tokens": 2,
            "total_tokens": 12,
            "reasoning_tokens": 0,
        },
        "attempts": [{
            "index": 1,
            "status": "COMPLETE",
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 2,
                "total_tokens": 12,
                "reasoning_tokens": 0,
            },
        }],
        "publication_authorized": False,
    }
    image_journal = {
        "version": 1,
        "provider": "image",
        "cap": 16,
        "attempts": [],
        "publication_authorized": False,
    }
    return lease, topic_input, producer, critic, journal, image_journal


class Acc1ResumeLockTests(unittest.TestCase):
    def test_resume_lease_binds_parent_evidence_and_current_caps(self):
        lease, topic, producer, critic, journal, image_journal = parent_evidence()
        resume = build_resume_lease(
            parent_lease=lease,
            topic_input=topic,
            producer_review=producer,
            critic_review=critic,
            openai_journal=journal,
            image_journal=image_journal,
            image_checkpoint={"version": 1, "entries": []},
            parent_run_id=101,
            run_id=202,
            run_attempt=1,
            head_sha=HEAD_SHA,
            repository=REPOSITORY,
            openai_call_cap=64,
            openai_token_cap=1_000_000,
            image_call_cap=16,
            ai33_call_cap=32,
        )
        validate_resume_lease(
            resume,
            repository=REPOSITORY,
            run_id=202,
            run_attempt=1,
            head_sha=HEAD_SHA,
            parent_run_id=101,
        )
        self.assertEqual(resume["parent_completed_image_attempts"], 0)
        self.assertIsNone(resume["parent_ambiguous_image_attempt_index"])
        self.assertEqual(
            resume["parent_image_checkpoint_sha256"],
            canonical_hash({"version": 1, "entries": []}),
        )
        tampered = copy.deepcopy(resume)
        tampered["caps"]["openai_call_cap"] = 63
        with self.assertRaisesRegex(ResumeLockError, "self hash"):
            validate_resume_lease(tampered, repository=REPOSITORY)

    def test_existing_resume_for_same_parent_blocks_second_resume(self):
        lease, topic, producer, critic, journal, image_journal = parent_evidence()
        resume = build_resume_lease(
            parent_lease=lease,
            topic_input=topic,
            producer_review=producer,
            critic_review=critic,
            openai_journal=journal,
            image_journal=image_journal,
            parent_run_id=101,
            run_id=202,
            run_attempt=1,
            head_sha=HEAD_SHA,
            repository=REPOSITORY,
            openai_call_cap=64,
            openai_token_cap=1_000_000,
            image_call_cap=16,
            ai33_call_cap=32,
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifact = root / "202-501"
            artifact.mkdir()
            (artifact / FILENAME).write_text(json.dumps(resume), encoding="utf-8")
            with self.assertRaisesRegex(ResumeLockError, "already has resume lease"):
                scan_existing(root, parent_run_id=101, repository=REPOSITORY)

    def test_chained_resume_binds_the_immediate_parent_resume(self):
        lease, topic, producer, critic, journal, image_journal = parent_evidence()
        first = build_resume_lease(
            parent_lease=lease, topic_input=topic, producer_review=producer,
            critic_review=critic, openai_journal=journal, image_journal=image_journal,
            parent_run_id=101,
            run_id=202, run_attempt=1, head_sha=HEAD_SHA,
            repository=REPOSITORY, openai_call_cap=64,
            openai_token_cap=1_000_000, image_call_cap=16, ai33_call_cap=32,
        )
        chained = build_resume_lease(
            parent_lease=lease, topic_input=topic, producer_review=producer,
            critic_review=critic, openai_journal=journal, image_journal=image_journal,
            parent_run_id=202,
            run_id=303, run_attempt=1, head_sha=HEAD_SHA,
            repository=REPOSITORY, openai_call_cap=64,
            openai_token_cap=1_000_000, image_call_cap=16, ai33_call_cap=32,
            parent_resume_lease=first,
        )
        validate_resume_lease(
            chained, repository=REPOSITORY, run_id=303, parent_run_id=202,
        )
        self.assertEqual(
            chained["parent_resume_lease_sha256"],
            canonical_hash(first),
        )
        third = build_resume_lease(
            parent_lease=lease, topic_input=topic, producer_review=producer,
            critic_review=critic, openai_journal=journal, image_journal=image_journal,
            parent_run_id=303,
            run_id=404, run_attempt=1, head_sha=HEAD_SHA,
            repository=REPOSITORY, openai_call_cap=64,
            openai_token_cap=1_000_000, image_call_cap=16, ai33_call_cap=32,
            parent_resume_lease=chained,
        )
        validate_resume_lease(
            third, repository=REPOSITORY, run_id=404, parent_run_id=303,
        )
        self.assertEqual(third["parent_spend_lease_sha256"], canonical_hash(lease))

    def test_final_ambiguous_image_attempt_is_consumed_not_retried(self):
        lease, topic, producer, critic, journal, image_journal = parent_evidence()
        image_journal["attempts"] = [
            {
                "index": 1, "status": "COMPLETE",
                "request_sha256": "1" * 64, "output_sha256": "2" * 64,
            },
            {
                "index": 2, "status": "AMBIGUOUS_ERROR",
                "request_sha256": "3" * 64, "error_type": "VectorEngineError",
            },
        ]
        resume = build_resume_lease(
            parent_lease=lease, topic_input=topic, producer_review=producer,
            critic_review=critic, openai_journal=journal,
            image_journal=image_journal, parent_run_id=101, run_id=202,
            run_attempt=1, head_sha=HEAD_SHA, repository=REPOSITORY,
            openai_call_cap=64, openai_token_cap=1_000_000,
            image_call_cap=16, ai33_call_cap=32,
        )
        self.assertEqual(resume["parent_ambiguous_image_attempt_index"], 2)
        validate_resume_lease(resume, repository=REPOSITORY)

        image_journal["attempts"].append({
            "index": 3, "status": "COMPLETE",
            "request_sha256": "4" * 64, "output_sha256": "5" * 64,
        })
        with self.assertRaisesRegex(ResumeLockError, "not completely resumable"):
            build_resume_lease(
                parent_lease=lease, topic_input=topic, producer_review=producer,
                critic_review=critic, openai_journal=journal,
                image_journal=image_journal, parent_run_id=101, run_id=202,
                run_attempt=1, head_sha=HEAD_SHA, repository=REPOSITORY,
                openai_call_cap=64, openai_token_cap=1_000_000,
                image_call_cap=16, ai33_call_cap=32,
            )

    def test_resume_lease_binds_completed_ai33_posts_and_in_progress_tts(self):
        lease, topic, producer, critic, journal, image_journal = parent_evidence()
        task_id = "task-one"
        ai33_journal = {
            "version": 1, "provider": "ai33", "cap": 32,
            "attempts": [{
                "index": 1, "status": "COMPLETE", "task_id": task_id,
                "request_sha256": "6" * 64, "response_sha256": "7" * 64,
            }],
            "publication_authorized": False,
        }
        tts_state = {
            "version": 3, "status": "IN_PROGRESS",
            "chunks": [{
                "chunk_id": "story__001", "status": "SUBMITTED", "task_id": task_id,
            }],
            "publication_authorized": False,
        }
        resume = build_resume_lease(
            parent_lease=lease, topic_input=topic, producer_review=producer,
            critic_review=critic, openai_journal=journal,
            image_journal=image_journal, ai33_journal=ai33_journal,
            tts_state=tts_state, parent_run_id=101, run_id=202,
            run_attempt=1, head_sha=HEAD_SHA, repository=REPOSITORY,
            openai_call_cap=64, openai_token_cap=1_000_000,
            image_call_cap=16, ai33_call_cap=32,
        )
        self.assertEqual(resume["parent_completed_ai33_attempts"], 1)
        self.assertEqual(
            resume["parent_ai33_journal_sha256"], canonical_hash(ai33_journal),
        )
        self.assertEqual(resume["parent_tts_state_sha256"], canonical_hash(tts_state))
        validate_resume_lease(resume, repository=REPOSITORY)

        broken_state = copy.deepcopy(tts_state)
        broken_state["chunks"][0]["task_id"] = "different-task"
        with self.assertRaisesRegex(ResumeLockError, "task IDs"):
            build_resume_lease(
                parent_lease=lease, topic_input=topic, producer_review=producer,
                critic_review=critic, openai_journal=journal,
                image_journal=image_journal, ai33_journal=ai33_journal,
                tts_state=broken_state, parent_run_id=101, run_id=202,
                run_attempt=1, head_sha=HEAD_SHA, repository=REPOSITORY,
                openai_call_cap=64, openai_token_cap=1_000_000,
                image_call_cap=16, ai33_call_cap=32,
            )

if __name__ == "__main__":
    unittest.main()
