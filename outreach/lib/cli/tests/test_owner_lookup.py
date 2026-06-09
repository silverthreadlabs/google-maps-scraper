"""`owner-lookup` is deprecated — it forwards to the unified `decision-makers`
stage. Owner-scalar projection (incl. the legacy `{name,title,linkedin}`
sidecar shape) is covered by test_decision_makers.py; here we only assert the
shim forwards and warns."""
import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
import lib.cli.owner_lookup as owner_lookup


class TestOwnerLookupShim(unittest.TestCase):
    def test_forwards_to_decision_makers_main(self):
        with mock.patch.object(owner_lookup, '_decision_makers_main', return_value=0) as m:
            with redirect_stderr(io.StringIO()):
                rc = owner_lookup.main(['software_ua_v2', '--apply'])
        self.assertEqual(rc, 0)
        m.assert_called_once_with(['software_ua_v2', '--apply'])

    def test_emits_deprecation_warning(self):
        buf = io.StringIO()
        with mock.patch.object(owner_lookup, '_decision_makers_main', return_value=0):
            with redirect_stderr(buf):
                owner_lookup.main([])
        self.assertIn('deprecated', buf.getvalue().lower())
        self.assertIn('decision-makers', buf.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
