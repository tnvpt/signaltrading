import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import socket
from pathlib import Path
import tempfile

from signaltrading.telegram_diagnose import diagnose, query, read_env_token, token_problem


class DiagnoseTests(unittest.TestCase):
    def test_env_file_bom_crlf_quotes_and_no_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"test.env"
            path.write_bytes(b'\xef\xbb\xbfexport TELEGRAM_BOT_TOKEN = "123:fake" # comment\r\nOTHER=$(command)\r\n')
            self.assertEqual(read_env_token(path), "123:fake")
            path.write_text("TELEGRAM_BOT_TOKEN='$(command)'\n")
            self.assertEqual(read_env_token(path), "$(command)")

    def test_env_duplicate_and_bad_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"test.env"
            for text in ("TELEGRAM_BOT_TOKEN='broken", "TELEGRAM_BOT_TOKEN=a\nTELEGRAM_BOT_TOKEN=b"):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    read_env_token(path)

    def test_safe_problem_reasons(self):
        self.assertEqual(token_problem(""), "TOKEN_EMPTY_OR_NOT_LOADED")
        self.assertEqual(token_problem("‘123:fake’"), "TOKEN_CONTAINS_SMART_QUOTES")
        self.assertEqual(token_problem("123:fake\u200b"), "TOKEN_CONTAINS_WHITESPACE_OR_HIDDEN_UNICODE")
        self.assertEqual(token_problem("bot123:fake"), "USE_TOKEN_ONLY_NOT_URL_OR_BOT_PREFIX")

    def test_token_missing_does_not_request(self):
        self.assertEqual(diagnose("", request=lambda *a: self.fail("network called")),
                         {"status": "TOKEN_MISSING_OR_BAD_FORMAT"})

    def test_webhook_preserved(self):
        calls = []
        def request(token, method):
            calls.append(method)
            return {"ok": True, "result": {"is_bot": True, "username": "testbot"}
                    if method == "getMe" else {"url": "https://private.example/secret"}}
        report = diagnose("123:fake", request)
        self.assertEqual(report["status"], "WEBHOOK_ACTIVE")
        self.assertEqual(calls, ["getMe", "getWebhookInfo"])
        self.assertNotIn("private.example", str(report))

    def test_chat_found_without_message_content(self):
        responses = iter([{"is_bot": True}, {"url": ""},
                          [{"message": {"chat": {"id": 123, "type": "private"}, "text": "sensitive"}}]])
        result = diagnose("123:fake", lambda *a: {"ok": True, "result": next(responses)})
        self.assertEqual(result["chats"], [{"chat_id": 123, "type": "private"}])
        self.assertNotIn("sensitive", str(result))

    def test_http_errors_sanitized(self):
        for code, expected in ((401, "TOKEN_REJECTED"), (409, "UPDATES_CONFLICT")):
            with patch("signaltrading.telegram_diagnose.urlopen", side_effect=HTTPError(
                    "https://contains-secret", code, "secret", {}, None)):
                result = query("123:fake", "getMe")
            self.assertEqual(result["error"], expected)
            self.assertNotIn("secret", str(result))

    def test_dns_error(self):
        with patch("signaltrading.telegram_diagnose.urlopen", side_effect=URLError(socket.gaierror())):
            self.assertEqual(query("123:fake", "getMe")["error"], "DNS_ERROR")