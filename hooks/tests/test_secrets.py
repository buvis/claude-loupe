"""Tests for hooks/loupe/secrets.py.

Every credential value here is synthetic. Each pattern gets a positive
(fires) and negative (placeholder or wrong shape stays silent) case,
because a false abort on every write is worse than a rare miss.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe.secrets import scan_for_secrets


class AwsAccessKeyTests(unittest.TestCase):
    def test_access_key_id_matches(self) -> None:
        content = 'aws_id = "AKIAJ4RJ2XKWDS4QZC7B"'
        self.assertEqual(scan_for_secrets(content), ["aws-access-key"])

    def test_session_key_prefix_matches(self) -> None:
        content = "ASIAQ7PLM2XKWDS4ZC7B"
        self.assertEqual(scan_for_secrets(content), ["aws-access-key"])

    def test_canonical_docs_key_is_a_placeholder(self) -> None:
        self.assertEqual(scan_for_secrets("AKIAIOSFODNN7EXAMPLE"), [])

    def test_lowercase_and_short_shapes_stay_silent(self) -> None:
        self.assertEqual(scan_for_secrets("akiaj4rj2xkwds4qzc7b"), [])
        self.assertEqual(scan_for_secrets("AKIA1234"), [])


class GithubTokenTests(unittest.TestCase):
    def test_ghp_token_matches(self) -> None:
        content = "ghp_F4kEt0k3nF4kEt0k3nF4kEt0k3nF4kEt0k3n"
        self.assertEqual(scan_for_secrets(content), ["github-token"])

    def test_fine_grained_pat_matches(self) -> None:
        content = "github_pat_11AB2C3D4E5F6G7H8I9J0KLMNPQ"
        self.assertEqual(scan_for_secrets(content), ["github-token"])

    def test_short_suffix_stays_silent(self) -> None:
        self.assertEqual(scan_for_secrets("ghp_short123"), [])

    def test_example_laden_token_is_a_placeholder(self) -> None:
        content = "gho_EXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLEE"
        self.assertEqual(scan_for_secrets(content), [])


class SlackTokenTests(unittest.TestCase):
    def test_bot_token_matches(self) -> None:
        content = "xoxb-210987654321-1098765432109-F4kEt0k3nSl4ck"
        self.assertEqual(scan_for_secrets(content), ["slack-token"])

    def test_unknown_token_letter_stays_silent(self) -> None:
        self.assertEqual(scan_for_secrets("xoxz-210987654321-1098765432109"), [])

    def test_placeholder_token_stays_silent(self) -> None:
        self.assertEqual(scan_for_secrets("xoxb-your-token-goes-here"), [])


class PrivateKeyTests(unittest.TestCase):
    def test_pem_block_with_body_matches(self) -> None:
        content = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA7x9J2mQv5TkW8LnR3sYb1cZd4eFg6hHj0iKl9mNo2pQr5sTu\n"
            "-----END RSA PRIVATE KEY-----\n"
        )
        self.assertEqual(scan_for_secrets(content), ["private-key"])

    def test_pkcs8_header_variant_matches(self) -> None:
        content = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgVcB3aBhN6bLnP1qJ\n"
        )
        self.assertEqual(scan_for_secrets(content), ["private-key"])

    def test_header_in_prose_stays_silent(self) -> None:
        content = "Never commit a -----BEGIN RSA PRIVATE KEY----- block to git."
        self.assertEqual(scan_for_secrets(content), [])

    def test_header_with_angle_placeholder_stays_silent(self) -> None:
        content = "-----BEGIN PRIVATE KEY-----\n<your key here>\n"
        self.assertEqual(scan_for_secrets(content), [])

    def test_dash_divider_after_header_is_not_key_material(self) -> None:
        content = "-----BEGIN PRIVATE KEY----- goes below\n" + "-" * 50 + "\n"
        self.assertEqual(scan_for_secrets(content), [])


class JwtTests(unittest.TestCase):
    def test_three_segment_token_matches(self) -> None:
        content = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIiwiaWF0IjoxNTE2MjM5MDIyfQ"
            ".TJVA95OrM7E2cBab30RMHrHDcEfxjoYZgeFONFh7HgQ"
        )
        self.assertEqual(scan_for_secrets(content), ["jwt"])

    def test_single_segment_stays_silent(self) -> None:
        self.assertEqual(scan_for_secrets("eyJhbGciOiJIUzI1NiJ9"), [])

    def test_two_segments_stay_silent(self) -> None:
        content = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwfQ"
        self.assertEqual(scan_for_secrets(content), [])


class ConnectionStringTests(unittest.TestCase):
    def test_embedded_password_matches(self) -> None:
        content = "postgres://svc_user:p8fR2vZq9wLx4T@db.internal.corp:5432/prod"
        self.assertEqual(scan_for_secrets(content), ["connection-string"])

    def test_stopword_password_stays_silent(self) -> None:
        content = "postgres://user:pass@db.internal.corp/app"
        self.assertEqual(scan_for_secrets(content), [])

    def test_interpolated_password_stays_silent(self) -> None:
        content = "mysql://root:${DB_PASS}@db.internal.corp"
        self.assertEqual(scan_for_secrets(content), [])

    def test_localhost_dev_credentials_stay_silent(self) -> None:
        content = "postgres://dev:s3cr3tpw9@localhost:5432/dev"
        self.assertEqual(scan_for_secrets(content), [])

    def test_example_dot_com_host_stays_silent(self) -> None:
        content = "https://alice:realLpw123@www.example.com/path"
        self.assertEqual(scan_for_secrets(content), [])


class CredentialAssignmentTests(unittest.TestCase):
    def test_long_quoted_value_matches(self) -> None:
        content = 'api_key = "sk-9f8g7h6j5k4l3m2n1p0q"'
        self.assertEqual(scan_for_secrets(content), ["credential-assignment"])

    def test_high_entropy_json_value_matches(self) -> None:
        content = '"password": "tR7#kPa2!9Vb@qWz"'
        self.assertEqual(scan_for_secrets(content), ["credential-assignment"])

    def test_ruby_hash_rocket_matches(self) -> None:
        content = "token => 'Zk8qLm3vXw9RtY5uPn2b'"
        self.assertEqual(scan_for_secrets(content), ["credential-assignment"])

    def test_annotated_python_assignment_matches(self) -> None:
        content = 'api_key: str = "Zk8qLm3vXw9RtY5uPn2b"'
        self.assertEqual(scan_for_secrets(content), ["credential-assignment"])

    def test_placeholder_values_stay_silent(self) -> None:
        for content in (
            'api_key = "changeme-changeme"',
            'password = "<your password here>"',
            'token = "${GITHUB_TOKEN}"',
            'secret = "f-string {value} here"',
        ):
            with self.subTest(content=content):
                self.assertEqual(scan_for_secrets(content), [])

    def test_low_entropy_short_value_stays_silent(self) -> None:
        self.assertEqual(scan_for_secrets('secret = "aaaaaaaaaaaaaaaa"'), [])

    def test_comparison_is_not_an_assignment(self) -> None:
        content = 'if password == "tR7#kPa2!9Vb@qWz":'
        self.assertEqual(scan_for_secrets(content), [])

    def test_prose_with_spaces_stays_silent(self) -> None:
        content = 'password = "correct horse battery staple"'
        self.assertEqual(scan_for_secrets(content), [])

    def test_non_credential_identifier_stays_silent(self) -> None:
        content = 'monkey = "Zk8qLm3vXw9RtY5uPn2b"'
        self.assertEqual(scan_for_secrets(content), [])


class EnvAssignmentTests(unittest.TestCase):
    def test_unquoted_env_value_matches(self) -> None:
        content = "API_KEY=9f3Kx7Qw2RvT8bNp1LzY"
        self.assertEqual(scan_for_secrets(content), ["credential-assignment"])

    def test_unquoted_high_entropy_value_matches(self) -> None:
        content = "DB_PASSWORD=p8fR2vZq9wLx4Tq2"
        self.assertEqual(scan_for_secrets(content), ["credential-assignment"])

    def test_function_reference_without_digits_stays_silent(self) -> None:
        self.assertEqual(scan_for_secrets("token=generate_access_token"), [])

    def test_numeric_id_stays_silent(self) -> None:
        self.assertEqual(scan_for_secrets("session_token=12345678901234"), [])

    def test_test_marker_stays_silent(self) -> None:
        self.assertEqual(scan_for_secrets("TOKEN=testtoken1234567890"), [])


class ScanBehaviorTests(unittest.TestCase):
    def test_clean_content_yields_empty_list(self) -> None:
        content = "def add(a, b):\n    return a + b\n"
        self.assertEqual(scan_for_secrets(content), [])

    def test_empty_content_yields_empty_list(self) -> None:
        self.assertEqual(scan_for_secrets(""), [])

    def test_categories_dedupe_and_preserve_order(self) -> None:
        content = (
            "AKIAJ4RJ2XKWDS4QZC7B\n"
            "ASIAQ7PLM2XKWDS4ZC7B\n"
            "xoxb-210987654321-1098765432109-F4kEt0k3nSl4ck\n"
        )
        self.assertEqual(
            scan_for_secrets(content), ["aws-access-key", "slack-token"]
        )


if __name__ == "__main__":
    unittest.main()
