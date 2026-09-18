import io
import unittest
from contextlib import redirect_stderr

from stitch_harness.cli import main


class HarnessCliTests(unittest.TestCase):
    def test_no_arguments_returns_contract_exit_code(self):
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            code = main([])

        self.assertEqual(code, 2)
        self.assertIn("usage:", stderr.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
