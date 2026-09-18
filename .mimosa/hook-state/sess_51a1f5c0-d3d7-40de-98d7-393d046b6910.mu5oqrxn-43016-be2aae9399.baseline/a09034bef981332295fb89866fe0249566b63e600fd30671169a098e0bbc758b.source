import unittest

from stitch_harness.assets import ALLOWED_DOWNLOAD_HOSTS, _download_url_allowed


class DownloadAllowlistTests(unittest.TestCase):
    """Pin the download allowlist boundary.

    The allowlist is a security control: it decides which hosts the local asset
    tool may fetch from. Adding an entry is only safe if lookalike hosts cannot
    ride along on the suffix match, so both directions are asserted here.
    """

    ALLOWED = (
        "https://lh3.googleusercontent.com/aida/example",
        "https://contribution.usercontent.google.com/download",
        "https://www.gstatic.com/example.png",
        "https://storage.googleapis.com/bucket/object",
        "https://stitch.withgoogle.com/download",
        "https://labs.withgoogle.com/example",
        "https://withgoogle.com/example",
    )

    REJECTED = (
        # not Google-owned
        "https://example.com/download",
        "https://withgoogle.com.evil.example/download",
        "https://stitch.withgoogle.com.evil.example/download",
        "https://evil-withgoogle.com/download",
        "https://notwithgoogle.com/download",
        "https://evilgoogle.com/download",
        "https://mygoogleusercontent.com/download",
        # right host, unsafe transport or authority
        "http://stitch.withgoogle.com/download",
        "https://user:password@stitch.withgoogle.com/download",
        "https://user@stitch.withgoogle.com/download",
    )

    def test_declared_allowlist_entries_are_the_expected_google_families(self):
        self.assertEqual(
            ALLOWED_DOWNLOAD_HOSTS,
            ("googleusercontent.com", "googleapis.com", "google.com", "gstatic.com", "withgoogle.com"),
        )

    def test_google_owned_hosts_are_allowed(self):
        for url in self.ALLOWED:
            with self.subTest(url=url):
                self.assertTrue(_download_url_allowed(url), url)

    def test_lookalike_and_unsafe_urls_are_rejected(self):
        for url in self.REJECTED:
            with self.subTest(url=url):
                self.assertFalse(_download_url_allowed(url), url)


if __name__ == "__main__":
    unittest.main()
