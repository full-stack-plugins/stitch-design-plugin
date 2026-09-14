import io
import http.client
import json
import os
import tempfile
import urllib.error
import unittest
from email.message import Message
from pathlib import Path
from unittest import mock

from stitch_harness.assets import AssetError, LocalAssetManager, UnknownAssetWriteResult, local_tool_definitions


class Response(io.BytesIO):
    def __init__(self, body: bytes, content_type: str, status: int = 200):
        super().__init__(body)
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(body))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class LocalAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def test_local_tools_have_complete_namespaced_contracts(self):
        tools = local_tool_definitions()
        self.assertEqual(
            {tool["name"] for tool in tools},
            {"stitch_local_upload_asset", "stitch_local_download_assets"},
        )
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertEqual(tool["outputSchema"]["type"], "object")
            self.assertIsInstance(tool["annotations"]["readOnlyHint"], bool)
            self.assertIsInstance(tool["annotations"]["openWorldHint"], bool)
        download = next(tool for tool in tools if tool["name"] == "stitch_local_download_assets")
        self.assertFalse(download["annotations"]["readOnlyHint"])
        self.assertFalse(download["annotations"]["idempotentHint"])
        self.assertIn("screenNames", download["inputSchema"]["properties"])
        self.assertEqual(
            download["inputSchema"]["properties"]["referencedAssetPolicy"]["default"],
            "best_effort",
        )
        self.assertIn("warnings", download["outputSchema"]["properties"])

    def test_upload_rejects_unsupported_symlink_and_oversize_before_transport(self):
        target = self.root / "payload.exe"
        target.write_bytes(b"x")
        link = self.root / "payload.png"
        link.symlink_to(target)
        calls = []
        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=lambda *a, **k: calls.append(a))
        for path in (target, link):
            with self.subTest(path=path), self.assertRaises(AssetError):
                manager.upload_asset("123", path)
        large = self.root / "large.png"
        large.write_bytes(b"x" * (10 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(AssetError, "size"):
            manager.upload_asset("123", large)
        self.assertEqual(calls, [])

    def test_upload_uses_one_official_https_request_and_returns_only_ids(self):
        source = self.root / "screen.html"
        source.write_text("<main>demo</main>", encoding="utf-8")
        calls = []

        def transport(request, **kwargs):
            calls.append((request, kwargs))
            body = {"results": [{"screen": {"name": "projects/123/screens/" + "1" * 19, "private": "ignore"}}]}
            return Response(json.dumps(body).encode(), "application/json")

        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=transport)
        result = manager.upload_asset("123", source, title="Demo", create_screen_instances=True)

        self.assertEqual(result, {"screens": [{"name": "projects/123/screens/" + "1" * 19}]})
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].full_url.startswith("https://stitch.googleapis.com/"))
        self.assertNotIn("secret", json.dumps(result))

    def test_upload_ambiguous_failures_are_unknown_writes(self):
        source = self.root / "screen.html"
        source.write_text("<main>demo</main>", encoding="utf-8")
        failures = (
            urllib.error.HTTPError("https://stitch.googleapis.com", 408, "timeout", {}, io.BytesIO()),
            urllib.error.HTTPError("https://stitch.googleapis.com", 503, "unavailable", {}, io.BytesIO()),
            urllib.error.URLError("disconnected"),
            http.client.IncompleteRead(b"partial"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                manager = LocalAssetManager(
                    secret_provider=lambda: "secret",
                    transport=lambda *_args, failure=failure, **_kwargs: (_ for _ in ()).throw(failure),
                )
                with self.assertRaises(UnknownAssetWriteResult):
                    manager.upload_asset("123", source)
        manager = LocalAssetManager(
            secret_provider=lambda: "secret",
            transport=lambda *_args, **_kwargs: Response(b"{}", "application/json"),
        )
        with self.assertRaises(UnknownAssetWriteResult):
            manager.upload_asset("123", source)

    @unittest.skipIf(os.name == "nt", "Windows symlink creation requires privileges")
    def test_upload_rejects_a_symlink_in_any_path_component(self):
        real = self.root / "real"
        real.mkdir()
        source = real / "screen.html"
        source.write_text("<main>demo</main>", encoding="utf-8")
        linked = self.root / "linked"
        linked.symlink_to(real, target_is_directory=True)
        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=lambda *_a, **_k: None)
        with self.assertRaisesRegex(AssetError, "symlink"):
            manager.upload_asset("123", linked / "screen.html")

    def test_upload_reads_through_safe_descriptor_not_path_read_bytes(self):
        source = self.root / "screen.html"
        source.write_text("<main>demo</main>", encoding="utf-8")
        body = {"results": [{"screen": {"name": "projects/123/screens/" + "a" * 32}}]}
        manager = LocalAssetManager(
            secret_provider=lambda: "secret",
            transport=lambda *_args, **_kwargs: Response(json.dumps(body).encode(), "application/json"),
        )
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unsafe path read")):
            self.assertEqual(len(manager.upload_asset("123", source)["screens"]), 1)

    def test_download_enforces_https_host_type_size_and_atomic_publication(self):
        output = self.root / "export"
        calls = []
        responses = {
            "https://lh3.googleusercontent.com/html": Response(b"<main>ok</main>", "text/html"),
            "https://lh3.googleusercontent.com/image": Response(b"\x89PNG\r\n\x1a\n", "image/png"),
        }

        def transport(request, **kwargs):
            calls.append(request.full_url)
            return responses[request.full_url]

        screens = [{
            "name": "projects/123/screens/" + "a" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
            "screenshot": {"downloadUrl": "https://lh3.googleusercontent.com/image"},
        }]
        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=transport)
        result = manager.download_assets("123", output, screens=screens)

        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["files"]), 2)
        self.assertTrue(all((output / item["path"]).is_file() for item in result["files"]))
        self.assertFalse(any(path.name.startswith(".") for path in output.rglob("*")))

        bad = [{"name": screens[0]["name"], "htmlCode": {"downloadUrl": "http://example.com/private"}}]
        with self.assertRaisesRegex(AssetError, "HTTPS"):
            manager.download_assets("123", self.root / "bad", screens=bad)

    def test_download_rejects_containment_escape_and_leaves_no_partial_output(self):
        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=lambda *a, **k: None)
        with self.assertRaisesRegex(AssetError, "contained"):
            manager.download_assets("123", self.root / "out", assets_subdir="../escape", screens=[])
        self.assertFalse((self.root / "out").exists())

    def test_asset_paths_must_be_absolute(self):
        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=lambda *a, **k: None)
        with self.assertRaisesRegex(AssetError, "absolute"):
            manager.upload_asset("123", Path("relative.png"))
        with self.assertRaisesRegex(AssetError, "absolute"):
            manager.download_assets("123", Path("relative-output"), screens=[])

    def test_html_export_downloads_allowlisted_referenced_assets(self):
        output = self.root / "export-with-assets"
        html = b'<main><img src="https://lh3.googleusercontent.com/logo"></main>'
        responses = {
            "https://lh3.googleusercontent.com/html": Response(html, "text/html"),
            "https://lh3.googleusercontent.com/logo": Response(b"\x89PNG\r\n\x1a\n", "image/png"),
        }
        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=lambda request, **_: responses[request.full_url])
        screens = [{
            "name": "projects/123/screens/" + "b" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
        }]

        result = manager.download_assets("123", output, screens=screens)

        self.assertEqual(result["count"], 2)
        self.assertTrue(any("referenced" in item["path"] for item in result["files"]))

    def test_html_export_accepts_https_assets_from_non_google_public_cdn(self):
        output = self.root / "export-with-public-cdn"
        html = b'<script src="https://cdn.tailwindcss.com"></script>'
        responses = {
            "https://lh3.googleusercontent.com/html": Response(html, "text/html"),
            "https://cdn.tailwindcss.com": Response(b"window.tailwind = {};", "application/javascript"),
        }
        manager = LocalAssetManager(
            secret_provider=lambda: "secret",
            transport=lambda request, **_: responses[request.full_url],
        )
        screens = [{
            "name": "projects/123/screens/" + "c" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
        }]

        result = manager.download_assets("123", output, screens=screens)

        self.assertEqual(result["count"], 2)
        self.assertTrue(any(item["mime"] == "application/javascript" for item in result["files"]))

    def test_html_export_best_effort_keeps_primary_files_when_safe_reference_fails(self):
        output = self.root / "export-best-effort-reference-failure"
        html = b'<script src="https://cdn.example.com/app.js"></script>'

        def transport(request, **_):
            if request.full_url == "https://lh3.googleusercontent.com/html":
                return Response(html, "text/html")
            raise urllib.error.URLError("temporary CDN failure")

        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=transport)
        screens = [{
            "name": "projects/123/screens/" + "f" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
        }]

        result = manager.download_assets("123", output, screens=screens)

        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["warnings"][0]["kind"], "referenced_asset_skipped")
        self.assertEqual(result["warnings"][0]["host"], "cdn.example.com")
        self.assertNotIn("app.js", json.dumps(result["warnings"]))
        self.assertTrue((output / result["files"][0]["path"]).is_file())

    def test_html_export_strict_rejects_safe_reference_failure(self):
        output = self.root / "export-strict-reference-failure"
        html = b'<script src="https://cdn.example.com/app.js"></script>'

        def transport(request, **_):
            if request.full_url == "https://lh3.googleusercontent.com/html":
                return Response(html, "text/html")
            raise urllib.error.URLError("temporary CDN failure")

        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=transport)
        screens = [{
            "name": "projects/123/screens/" + "f" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
        }]

        with self.assertRaisesRegex(AssetError, "referenced asset download failed"):
            manager.download_assets(
                "123", output, screens=screens, referenced_asset_policy="strict"
            )
        self.assertFalse((output / "assets").exists())

    def test_html_export_best_effort_does_not_relax_reference_size_limit(self):
        output = self.root / "export-best-effort-oversize"
        html = b'<script src="https://cdn.example.com/oversize.js"></script>'
        responses = {
            "https://lh3.googleusercontent.com/html": Response(html, "text/html"),
            "https://cdn.example.com/oversize.js": Response(
                b"x" * (25 * 1024 * 1024 + 1),
                "application/javascript",
            ),
        }
        manager = LocalAssetManager(
            secret_provider=lambda: "secret",
            transport=lambda request, **_: responses[request.full_url],
        )
        screens = [{
            "name": "projects/123/screens/" + "f" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
        }]

        with self.assertRaisesRegex(AssetError, "maximum size"):
            manager.download_assets("123", output, screens=screens)
        self.assertFalse((output / "assets").exists())

    def test_multi_screen_export_enforces_final_file_count_limit(self):
        output = self.root / "export-file-count-limit"
        html = b'<script src="https://cdn.example.com/shared.js"></script>'
        def transport(request, **_):
            if request.full_url == "https://lh3.googleusercontent.com/html":
                return Response(html, "text/html")
            if request.full_url == "https://lh3.googleusercontent.com/image":
                return Response(b"\x89PNG\r\n\x1a\n", "image/png")
            return Response(b"window.shared = true;", "application/javascript")
        screens = [
            {
                "name": "projects/123/screens/" + character * 32,
                "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
                "screenshot": {"downloadUrl": "https://lh3.googleusercontent.com/image"},
            }
            for character in ("a", "b")
        ]
        manager = LocalAssetManager(
            secret_provider=lambda: "secret",
            transport=transport,
        )

        with mock.patch("stitch_harness.assets.MAX_EXPORT_FILES", 3):
            with self.assertRaisesRegex(AssetError, "at most 3 files"):
                manager.download_assets("123", output, screens=screens)
        self.assertFalse((output / "assets").exists())

    def test_best_effort_file_limit_counts_only_successfully_exported_references(self):
        output = self.root / "export-skipped-references-dont-count"
        html = (
            b'<script src="https://cdn-one.example.com/app.js"></script>'
            b'<link href="https://cdn-two.example.com/app.css" rel="stylesheet">'
        )

        def transport(request, **_):
            if request.full_url == "https://lh3.googleusercontent.com/html":
                return Response(html, "text/html")
            raise urllib.error.URLError("temporary CDN failure")

        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=transport)
        screens = [{
            "name": "projects/123/screens/" + "c" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
        }]

        with mock.patch("stitch_harness.assets.MAX_EXPORT_FILES", 1):
            result = manager.download_assets("123", output, screens=screens)

        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["warnings"]), 2)
        self.assertTrue((output / result["files"][0]["path"]).is_file())

    def test_best_effort_enforces_independent_referenced_url_budget(self):
        output = self.root / "export-reference-request-budget"
        html = "".join(
            f'<script src="https://cdn.example.com/{index}.js"></script>'
            for index in range(501)
        ).encode("utf-8")

        def transport(request, **_):
            if request.full_url == "https://lh3.googleusercontent.com/html":
                return Response(html, "text/html")
            raise urllib.error.URLError("temporary CDN failure")

        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=transport)
        screens = [{
            "name": "projects/123/screens/" + "d" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
        }]

        with self.assertRaisesRegex(AssetError, "at most 500 referenced URLs"):
            manager.download_assets("123", output, screens=screens)
        self.assertFalse((output / "assets").exists())

    def test_html_export_rejects_unsafe_non_google_references(self):
        unsafe_references = (
            "https://user:password@cdn.example.com/app.js",
            "https://localhost/app.js",
            "https://127.0.0.1/app.js",
            "https://[::1]/app.js",
        )
        for index, reference in enumerate(unsafe_references):
            with self.subTest(reference=reference):
                html = f'<script src="{reference}"></script>'.encode()
                responses = {
                    "https://lh3.googleusercontent.com/html": Response(html, "text/html"),
                }
                manager = LocalAssetManager(
                    secret_provider=lambda: "secret",
                    transport=lambda request, **_: responses[request.full_url],
                )
                screens = [{
                    "name": "projects/123/screens/" + "d" * 32,
                    "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
                }]
                with self.assertRaisesRegex(AssetError, "safe public HTTPS"):
                    manager.download_assets(
                        "123",
                        self.root / f"unsafe-reference-{index}",
                        screens=screens,
                    )

    def test_html_export_ignores_non_https_references(self):
        html = b'<script src="http://cdn.example.com/app.js"></script>'
        calls = []
        responses = {
            "https://lh3.googleusercontent.com/html": Response(html, "text/html"),
        }

        def transport(request, **_):
            calls.append(request.full_url)
            return responses[request.full_url]

        manager = LocalAssetManager(secret_provider=lambda: "secret", transport=transport)
        screens = [{
            "name": "projects/123/screens/" + "e" * 32,
            "htmlCode": {"downloadUrl": "https://lh3.googleusercontent.com/html"},
        }]

        result = manager.download_assets("123", self.root / "ignore-http", screens=screens)

        self.assertEqual(result["count"], 1)
        self.assertEqual(calls, ["https://lh3.googleusercontent.com/html"])

    def test_download_rejects_bad_image_magic_and_excessive_screen_count(self):
        screen = {
            "name": "projects/123/screens/" + "a" * 32,
            "screenshot": {"downloadUrl": "https://lh3.googleusercontent.com/image"},
        }
        manager = LocalAssetManager(
            secret_provider=lambda: "secret",
            transport=lambda *_args, **_kwargs: Response(b"not-png", "image/png"),
        )
        with self.assertRaisesRegex(AssetError, "content"):
            manager.download_assets("123", self.root / "bad-magic", screens=[screen])
        with self.assertRaisesRegex(AssetError, "screens"):
            manager.download_assets("123", self.root / "too-many", screens=[screen] * 101)


if __name__ == "__main__":
    unittest.main()
