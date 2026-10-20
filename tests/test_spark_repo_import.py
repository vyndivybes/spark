import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_repo_import import (
    RepoImportError,
    _read_license,
    dependency_map,
    import_evidence,
    parse_github_url,
)


class UrlParsingTests(unittest.TestCase):
    def test_accepts_plain_and_git_and_trailing_slash(self):
        self.assertEqual(parse_github_url("https://github.com/psf/requests"), ("psf", "requests"))
        self.assertEqual(parse_github_url("https://github.com/psf/requests.git"), ("psf", "requests"))
        self.assertEqual(parse_github_url("https://github.com/psf/requests/"), ("psf", "requests"))

    def test_rejects_non_github_and_non_https(self):
        for bad in ("http://github.com/a/b", "https://evil.com/a/b",
                    "git@github.com:a/b.git", "https://github.com/a",
                    "https://gitlab.com/a/b", "file:///c:/x"):
            with self.subTest(bad=bad):
                with self.assertRaises(RepoImportError):
                    parse_github_url(bad)

    def test_rejects_non_string(self):
        with self.assertRaises(RepoImportError):
            parse_github_url(None)


class LicenseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_mit_is_permissive(self):
        (self.root / "LICENSE").write_text("MIT License\nPermission is hereby granted")
        spdx, klass, name, _ = _read_license(self.root)
        self.assertEqual((spdx, klass), ("MIT", "permissive"))

    def test_agpl_is_strong_copyleft(self):
        (self.root / "COPYING").write_text("GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3")
        self.assertEqual(_read_license(self.root)[:2], ("AGPL", "strong-copyleft"))

    def test_apache_is_permissive(self):
        (self.root / "LICENSE").write_text("Apache License\nVersion 2.0")
        self.assertEqual(_read_license(self.root)[:2], ("Apache-2.0", "permissive"))

    def test_no_license_reports_none(self):
        self.assertEqual(_read_license(self.root)[:3], (None, "none", None))


class DependencyMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_combines_manifests(self):
        (self.root / "package.json").write_text(
            '{"dependencies":{"react":"^18.0.0"},"devDependencies":{"vite":"^5"}}')
        (self.root / "requirements.txt").write_text("requests>=2.31\n# c\nflask\n")
        (self.root / "pyproject.toml").write_text('dependencies = ["httpx>=0.27"]\n')
        result = dependency_map(self.root)
        self.assertIn("react", result["python"])
        self.assertIn("requests", result["python"])
        self.assertIn("httpx", result["python"])
        self.assertEqual(result["node"], ["vite"])
        self.assertGreaterEqual(result["count"], 4)

    def test_missing_manifests_is_empty(self):
        result = dependency_map(self.root)
        self.assertEqual(result["count"], 0)


class ImportEvidenceTests(unittest.TestCase):
    """Exercise clone-free paths by stubbing _clone to populate the checkout."""

    def _fake_clone(self, files):
        def clone(url, destination, *, timeout):
            destination.mkdir(parents=True, exist_ok=True)
            for relative, text in files.items():
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
        return clone

    def test_assemble_evidence_without_executing_repo_code(self):
        files = {
            "LICENSE": "MIT License\nPermission is hereby granted",
            "README.md": "# Demo\nA sample.",
            "src/main.py": "print('hello')\n",
            "package.json": '{"dependencies":{"express":"^4"}}',
        }
        with mock.patch("spark_repo_import._clone", side_effect=self._fake_clone(files)):
            evidence = import_evidence("https://github.com/owner/demo")
        self.assertEqual(evidence["repository"], "owner/demo")
        self.assertFalse(evidence["imported"]["code_executed"])
        self.assertTrue(evidence["imported"]["hooks_disabled"])
        self.assertEqual(evidence["license"]["spdx"], "MIT")
        self.assertTrue(evidence["license"]["permissive"])
        self.assertIn("express", evidence["dependency_map"]["python"])
        paths = {s["path"] for s in evidence["sources"]}
        self.assertTrue(any(p.endswith("main.py") for p in paths))

    def test_temp_clone_is_removed_even_on_success(self):
        created = {}

        def clone(url, destination, *, timeout):
            created["path"] = destination
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "README.md").write_text("# x\n")

        with mock.patch("spark_repo_import._clone", side_effect=clone):
            import_evidence("https://github.com/o/r")
        self.assertFalse(created["path"].exists())

    def test_rejects_missing_license_repos_as_all_rights_reserved(self):
        with mock.patch("spark_repo_import._clone", side_effect=self._fake_clone({"README.md": "# x\n"})):
            evidence = import_evidence("https://github.com/o/r")
        self.assertEqual(evidence["license"]["class"], "none")
        self.assertFalse(evidence["license"]["permissive"])

    def test_bad_url_rejected_before_any_clone(self):
        with mock.patch("spark_repo_import._clone") as clone:
            with self.assertRaises(RepoImportError):
                import_evidence("https://evil.com/o/r")
            clone.assert_not_called()

    def test_invalid_timeout_rejected(self):
        with self.assertRaises(RepoImportError):
            import_evidence("https://github.com/o/r", timeout=5)


if __name__ == "__main__":
    unittest.main()
