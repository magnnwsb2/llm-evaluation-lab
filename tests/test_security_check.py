"""Tests for the independent public-CI security gate; no actual secrets used."""

import unittest

from tools.security_check import scan_line, sensitive_filename


class SecurityCheckTests(unittest.TestCase):
    def test_sensitive_filenames_are_blocked(self):
        for path in (".env", "config/.env.prod", "keys/id_rsa", "id_ed25519", "cert/server.pem"):
            with self.subTest(path=path):
                self.assertTrue(sensitive_filename(path))

    def test_example_env_files_are_allowed(self):
        self.assertFalse(sensitive_filename(".env.example"))
        self.assertFalse(sensitive_filename("config/.env.sample"))
        self.assertFalse(sensitive_filename("README.md"))

    def test_concrete_credential_assignment_blocked(self):
        fake_assignment = "api_" + "key = " + "'synthetic-value'"
        self.assertIn("credential-assignment", scan_line(fake_assignment))
        fake_password = "pass" + "word: " + "not-a-real-credential"
        self.assertIn("credential-assignment", scan_line(fake_password))

    def test_safe_environment_reference(self):
        safe_line = "api_" + "key = os.environ.get('EXAMPLE_KEY')"
        self.assertNotIn("credential-assignment", scan_line(safe_line))

    def test_private_key_header_blocked_without_using_key(self):
        fake_header = "-----BEGIN " + "PRIVATE KEY-----"
        self.assertIn("private-key-header", scan_line(fake_header))

    def test_internal_addresses_are_only_review_items(self):
        self.assertIn("internal-endpoint-review", scan_line("https://localhost:8000/health"))
        self.assertEqual(scan_line("https://example.com/health"), ())

    def test_no_candidate_values_returned(self):
        synthetic = "api_" + "key = " + "'synthetic-only-value'"
        joined = "|".join(scan_line(synthetic))
        self.assertNotIn("synthetic-only-value", joined)


if __name__ == "__main__":
    unittest.main()
