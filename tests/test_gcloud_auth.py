import subprocess
import unittest
from unittest import mock

from stitch_harness import gcloud_auth
from stitch_harness.gcloud_auth import GcloudAdcAuth, GcloudAuthError


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class FakeRunner:
    """Route canned outcomes by command predicate and record every call."""

    def __init__(self, *rules):
        self.rules = list(rules)
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        for predicate, outcome in self.rules:
            if predicate(args):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError("unexpected command: " + " ".join(args))


def has_flag(flag):
    return lambda args: flag in args


TOKEN = has_flag("print-access-token")
QUIET_LOGIN = has_flag("--quiet")
PROBE_LOGIN = has_flag("--no-launch-browser")
CONFIG_PROJECT = has_flag("get-value")


def make_auth(runner, **overrides):
    defaults = dict(
        runner=runner,
        clock=FakeClock(),
        platform="sunos",
        env={},
        executable="/usr/bin/gcloud",
    )
    defaults.update(overrides)
    return GcloudAdcAuth(**defaults)


class ExecutableTests(unittest.TestCase):
    def test_explicit_executable_wins(self):
        runner = FakeRunner()
        auth = make_auth(runner, executable="/custom/gcloud")
        self.assertEqual(auth.find_executable(), "/custom/gcloud")

    def test_missing_executable_returns_none(self):
        with mock.patch.object(gcloud_auth.shutil, "which", return_value=None):
            auth = make_auth(FakeRunner(), executable=None)
            self.assertIsNone(auth.find_executable())

    def test_common_install_paths_are_checked(self):
        with mock.patch.object(gcloud_auth.shutil, "which", return_value=None), \
             mock.patch.object(gcloud_auth.Path, "is_file", return_value=True):
            auth = make_auth(FakeRunner(), platform="linux", executable=None)
            self.assertEqual(auth.find_executable(), "/usr/bin/gcloud")

    def test_windows_cmd_fallback(self):
        with mock.patch.object(gcloud_auth.shutil, "which", side_effect=[None, "C:/tools/gcloud.cmd"]):
            auth = make_auth(FakeRunner(), platform="win32", executable=None)
            self.assertEqual(auth.find_executable(), "C:/tools/gcloud.cmd")


class TokenTests(unittest.TestCase):
    def test_token_is_cached_within_ttl(self):
        clock = FakeClock()
        runner = FakeRunner((TOKEN, completed(0, "tok-1")))
        auth = make_auth(runner, clock=clock, token_ttl=600.0)

        self.assertEqual(auth.access_token(), "tok-1")
        clock.advance(599.0)
        self.assertEqual(auth.access_token(), "tok-1")
        self.assertEqual(len(runner.calls), 1)

        clock.advance(2.0)
        self.assertEqual(auth.access_token(), "tok-1")
        self.assertEqual(len(runner.calls), 2)

    def test_failed_probe_short_circuits_until_invalidation(self):
        runner = FakeRunner((TOKEN, OSError("boom")))
        auth = make_auth(runner)

        self.assertIsNone(auth.access_token())
        self.assertIsNone(auth.access_token())
        self.assertEqual(len(runner.calls), 1)

        auth.invalidate()
        self.assertIsNone(auth.access_token())
        self.assertEqual(len(runner.calls), 2)

    def test_disabled_by_env_flag(self):
        runner = FakeRunner((TOKEN, completed(0, "tok")))
        auth = make_auth(runner, env={"STITCH_DISABLE_ADC": "1"})
        self.assertTrue(auth.disabled())
        self.assertIsNone(auth.access_token())
        self.assertEqual(runner.calls, [])

    def test_has_credentials_requires_mintable_token(self):
        auth = make_auth(FakeRunner((TOKEN, completed(1))))
        self.assertFalse(auth.has_credentials())
        auth = make_auth(FakeRunner((TOKEN, completed(0, "tok"))))
        self.assertTrue(auth.has_credentials())


class QuotaProjectTests(unittest.TestCase):
    def test_env_overrides_win_in_order(self):
        auth = make_auth(FakeRunner(), env={"GOOGLE_CLOUD_PROJECT": "from-google-env", "STITCH_PROJECT_ID": "ignored"})
        self.assertEqual(auth.quota_project(), "from-google-env")

        auth = make_auth(FakeRunner(), env={"STITCH_PROJECT_ID": "from-stitch-env"})
        self.assertEqual(auth.quota_project(), "from-stitch-env")

    def test_falls_back_to_gcloud_config(self):
        runner = FakeRunner((CONFIG_PROJECT, completed(0, " my-project \n")))
        auth = make_auth(runner)
        self.assertEqual(auth.quota_project(), "my-project")
        self.assertIn("config", runner.calls[0])

    def test_config_failure_returns_none(self):
        runner = FakeRunner((CONFIG_PROJECT, completed(1)))
        auth = make_auth(runner)
        self.assertIsNone(auth.quota_project())


class LoginTests(unittest.TestCase):
    def test_successful_login_prints_url_and_verifies_token(self):
        runner = FakeRunner(
            (PROBE_LOGIN, completed(1, stderr="Go to https://accounts.google.com/o/oauth2/auth?abc to continue\n")),
            (QUIET_LOGIN, completed(0)),
            (TOKEN, completed(0, "fresh-token")),
        )
        auth = make_auth(runner, executable="/usr/bin/gcloud")

        with mock.patch("builtins.print") as printer:
            self.assertEqual(auth.login(), 0)
        printed = " ".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("https://accounts.google.com/o/oauth2/auth?abc", printed)
        self.assertEqual(len(runner.calls), 3)

    def test_missing_executable_reports_install_hint(self):
        with mock.patch.object(gcloud_auth.shutil, "which", return_value=None), \
             mock.patch.object(gcloud_auth.Path, "is_file", return_value=False), \
             mock.patch("sys.stderr") as stderr:
            auth = make_auth(FakeRunner(), executable=None)
            self.assertEqual(auth.login(), 1)
        written = "".join(str(call.args[0]) for call in stderr.write.call_args_list)
        self.assertIn("gcloud was not found", written)

    def test_disabled_login_returns_1(self):
        auth = make_auth(FakeRunner(), env={"STITCH_DISABLE_ADC": "yes"})
        self.assertEqual(auth.login(), 1)

    def test_failed_consent_returns_exit_code(self):
        runner = FakeRunner(
            (PROBE_LOGIN, completed(1)),
            (QUIET_LOGIN, completed(3)),
        )
        auth = make_auth(runner)
        self.assertEqual(auth.login(), 3)

    def test_consent_without_mintable_token_reports_fallback(self):
        runner = FakeRunner(
            (PROBE_LOGIN, completed(1)),
            (QUIET_LOGIN, completed(0)),
            (TOKEN, completed(1)),
        )
        auth = make_auth(runner)
        with mock.patch("sys.stderr") as stderr:
            self.assertEqual(auth.login(), 1)
        written = "".join(str(call.args[0]) for call in stderr.write.call_args_list)
        self.assertIn("no access token", written)

    def test_probe_timeout_does_not_abort_login(self):
        runner = FakeRunner(
            (PROBE_LOGIN, subprocess.TimeoutExpired(cmd="gcloud", timeout=5)),
            (QUIET_LOGIN, completed(0)),
            (TOKEN, completed(0, "tok")),
        )
        auth = make_auth(runner, executable="/usr/bin/gcloud")
        self.assertEqual(auth.login(), 0)


if __name__ == "__main__":
    unittest.main()
