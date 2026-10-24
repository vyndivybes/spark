import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_security_scan import (
    SecurityScanError,
    scan_code,
    scan_secrets,
    scan_sources,
)


class SecretScanTests(unittest.TestCase):
    def test_standard_form_content_type_is_not_a_random_secret(self):
        self.assertEqual(scan_secrets("headers = {'Content-Type': 'application/x-www-form-urlencoded'}"), [])

    def test_public_recovery_code_is_not_a_secret_but_assignments_still_are(self):
        self.assertEqual(scan_secrets('reason = "recovery_blocked_snapshot_integrity"'), [])
        self.assertIn('assigned_secret', {h['label'] for h in scan_secrets('password = "recovery_blocked_snapshot_integrity"')})
        self.assertIn('high_entropy_literal', {h['label'] for h in scan_secrets('reason = "recovery_blocked_snapshot_integrity_extra"')})

    def test_public_literal_exception_does_not_hide_assigned_secrets_or_near_matches(self):
        assigned = scan_secrets('password = "application/x-www-form-urlencoded"')
        self.assertIn('assigned_secret', {hit['label'] for hit in assigned})
        for value in ('application/x-www-form-urlencoded-extra', '9f4Aq7Zx2Lm8Pw3Rt6Yu1Io5Nb0Vc7Df'):
            with self.subTest(value=value):
                self.assertIn('high_entropy_literal', {hit['label'] for hit in scan_secrets('value = "' + value + '"')})

    def test_clean_source_has_no_findings(self):
        self.assertEqual(scan_secrets("def add(a, b):\n    return a + b\n"), [])

    def test_provider_tokens_are_detected(self):
        text = (
            'aws = "AKIA1234567890ABCDEF"\n'
            'gh = "ghp_' + 'A' * 36 + '"\n'
            'jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijKL"\n'
        )
        labels = {item["label"] for item in scan_secrets(text)}
        self.assertEqual(labels, {"aws_access_key", "github_token", "jwt"})

    def test_private_key_block_is_detected(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n"
        labels = {item["label"] for item in scan_secrets(text)}
        self.assertIn("private_key", labels)

    def test_assigned_secret_detected_but_placeholders_ignored(self):
        self.assertEqual(scan_secrets('password = "changeme_example"'), [])
        self.assertEqual(scan_secrets('password = "test_password_123"'), [])
        self.assertTrue(scan_secrets('api_key = "9f4Aq7Zx2Lm8Pw3Rt6Yu1Io5Nb0Vc"'))

    def test_findings_never_contain_full_secret(self):
        secret = "AKIA1234567890ABCDEF"
        finding = scan_secrets('key = "%s"' % secret)[0]
        self.assertNotIn(secret, finding["redacted"])

    def test_non_text_is_rejected(self):
        with self.assertRaises(SecurityScanError):
            scan_secrets(123)


class CodeScanTests(unittest.TestCase):
    def test_dangerous_constructs_detected(self):
        text = (
            "import os, pickle, subprocess\n"
            "os.system('ls')\n"
            "eval('2+2')\n"
            "exec('x=1')\n"
            "subprocess.run('x', shell=True)\n"
            "pickle.loads(data)\n"
        )
        labels = {item["label"] for item in scan_code(text)}
        self.assertIn("os_shell", labels)
        self.assertIn("eval_call", labels)
        self.assertIn("exec_call", labels)
        self.assertIn("shell_true", labels)
        self.assertIn("pickle_load", labels)

    def test_tls_and_private_ip_patterns(self):
        text = 'requests.get("http://192.168.1.50", verify=False)\n'
        labels = {item["label"] for item in scan_code(text)}
        self.assertIn("hardcoded_private_ip", labels)
        self.assertIn("tls_verification_disabled", labels)

    def test_clean_code_has_no_findings(self):
        self.assertEqual(scan_code("value = 2\nprint(value)\n"), [])

    def test_invalid_syntax_does_not_raise(self):
        self.assertEqual(scan_code("def (:\n"), [])


class ScanSourcesTests(unittest.TestCase):
    def test_secret_blocks_but_code_is_advisory(self):
        result = scan_sources({
            "a.py": 'key = "AKIA1234567890ABCDEF"\n',
            "b.py": "value = 1\n",
        })
        self.assertTrue(result["blocked"])
        self.assertEqual(result["secret_count"], 1)

    def test_code_only_does_not_block(self):
        result = scan_sources({"a.py": "eval('2+2')\n"})
        self.assertFalse(result["blocked"])
        self.assertEqual(result["secret_count"], 0)

    def test_signature_is_stable(self):
        first = scan_sources({"a.py": "eval('x')\n"})["signature"]
        second = scan_sources({"a.py": "eval('x')\n"})["signature"]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)


if __name__ == "__main__":
    unittest.main()
