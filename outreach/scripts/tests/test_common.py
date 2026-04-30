"""Tests for scripts/_common pipeline_lock."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class _LockTestBase(unittest.TestCase):
    """Patches OUTREACH_ROOT to a fresh temp dir per test so the lockfile
    lands somewhere disposable instead of in the real outreach/pipelines/."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.outreach_root = Path(self.tmpdir.name)
        (self.outreach_root / 'pipelines' / 'test_vertical').mkdir(parents=True)

        self.outreach_patch = patch('scripts._common.OUTREACH_ROOT', self.outreach_root)
        self.outreach_patch.start()
        self.addCleanup(self.outreach_patch.stop)

    @property
    def lockfile(self) -> Path:
        return self.outreach_root / 'pipelines' / 'test_vertical' / '.lock'


class TestPipelineLockHappyPath(_LockTestBase):
    def test_acquires_writes_payload_and_releases(self):
        from scripts._common import pipeline_lock

        self.assertFalse(self.lockfile.exists())
        with pipeline_lock('test_vertical', 'enrich'):
            self.assertTrue(self.lockfile.exists())
            payload = json.loads(self.lockfile.read_text())
            self.assertEqual(payload['pid'], os.getpid())
            self.assertEqual(payload['stage'], 'enrich')
            self.assertRegex(payload['since'],
                             r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$')

        # Released cleanly after a successful body.
        self.assertFalse(self.lockfile.exists())

    def test_releases_lock_on_exception(self):
        from scripts._common import pipeline_lock

        with self.assertRaises(ValueError):
            with pipeline_lock('test_vertical', 'enrich'):
                self.assertTrue(self.lockfile.exists())
                raise ValueError('body crashed')

        # The lock must come off even when the body raised — otherwise a
        # crashed run leaves the pipeline permanently stuck.
        self.assertFalse(self.lockfile.exists())


class TestPipelineLockContention(_LockTestBase):
    def test_refuses_when_held_by_live_pid(self):
        from scripts._common import pipeline_lock

        # Our own PID is alive — writing it should make the next acquire
        # refuse with exit 2.
        self.lockfile.write_text(json.dumps({
            'pid': os.getpid(),
            'stage': 'enrich',
            'since': '2026-04-30T10:00:00+00:00',
        }))

        with self.assertRaises(SystemExit) as cm:
            with pipeline_lock('test_vertical', 'validate'):
                self.fail("body must not execute when lock is held")
        self.assertEqual(cm.exception.code, 2)

        # Lockfile contents must remain intact — we didn't acquire, so we
        # mustn't have stomped on the holder's metadata.
        payload = json.loads(self.lockfile.read_text())
        self.assertEqual(payload['stage'], 'enrich')

    def test_reclaims_stale_lock_when_pid_not_alive(self):
        from scripts._common import pipeline_lock

        # PID 0 is reserved (kernel scheduler) and `os.kill(0, 0)` is
        # special — using it lets _pid_alive return False reliably without
        # the PID-reuse hazard of picking a "high number".
        self.lockfile.write_text(json.dumps({
            'pid': 0,
            'stage': 'crashed',
            'since': '2026-04-30T08:00:00+00:00',
        }))

        with pipeline_lock('test_vertical', 'reclaim'):
            payload = json.loads(self.lockfile.read_text())
            self.assertEqual(payload['pid'], os.getpid())
            self.assertEqual(payload['stage'], 'reclaim')

        self.assertFalse(self.lockfile.exists())

    def test_corrupt_lockfile_is_reclaimed(self):
        from scripts._common import pipeline_lock

        self.lockfile.write_text('{ this is not valid json')

        with pipeline_lock('test_vertical', 'reclaim'):
            payload = json.loads(self.lockfile.read_text())
            self.assertEqual(payload['pid'], os.getpid())
            self.assertEqual(payload['stage'], 'reclaim')


class TestPipelineLockSafety(_LockTestBase):
    def test_does_not_remove_someone_elses_lock_on_exit(self):
        # If a manual `rm` or another acquirer overwrites the lockfile
        # mid-run, our context manager must not delete the new owner's
        # lock when our `with` block exits.
        from scripts._common import pipeline_lock

        with pipeline_lock('test_vertical', 'enrich'):
            # Simulate a different process taking over (don't do this for
            # real — the contention test covers the actual refuse path).
            self.lockfile.write_text(json.dumps({
                'pid': os.getpid() + 99999,
                'stage': 'someone_else',
                'since': '2026-04-30T11:00:00+00:00',
            }))

        # The "other" lock must still be there.
        self.assertTrue(self.lockfile.exists())
        payload = json.loads(self.lockfile.read_text())
        self.assertEqual(payload['stage'], 'someone_else')

        # Clean up so the temp dir's removal doesn't trip on it.
        self.lockfile.unlink()


if __name__ == '__main__':
    unittest.main(verbosity=2)
