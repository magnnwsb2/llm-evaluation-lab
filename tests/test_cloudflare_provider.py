"""Offline-only tests for the Cloudflare adapter; never use real credentials."""

import io
import json
import socket
import unittest
import urllib.error
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from llm_eval.contracts import Case, Assertion, ContractError, load_experiment
from llm_eval.providers.cloudflare import (
    MAX_RESPONSE_BYTES,
    ProviderError,
    _NoRedirects,
    _http_error_category,
    _post_json,
    infer,
)
from llm_eval.scoring import grade


class CloudflareAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.experiment = load_experiment(
            "experiments/smoke-001.json", Path(__file__).resolve().parents[1]
        )
        cls.case = cls.experiment.cases[0]

    def setUp(self):
        self.account_id = "a" * 32
        self.api_token = "synthetic-test-token"

    def test_one_request_payload_and_measured_client_latency(self):
        calls = []
        def fake_transport(url, token, body):
            calls.append((url, token, body))
            return {"success": True, "result": {"response": " OK "}}

        clock = iter([10.0, 10.2])
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = infer(
                self.experiment, self.case, account_id=self.account_id,
                api_token=self.api_token, transport=fake_transport,
                clock=lambda: next(clock),
            )
        self.assertEqual(result.text, " OK ")
        self.assertTrue(199 <= result.latency_ms <= 201)
        self.assertEqual(len(calls), 1)
        url, token, body = calls[0]
        self.assertEqual(
            url,
            "https://api.cloudflare.com/client/v4/accounts/" + self.account_id +
            "/ai/run/@cf/meta/llama-3.1-8b-instruct-fp8",
        )
        self.assertEqual(token, self.api_token)
        self.assertEqual(body["messages"], [{"role": "user", "content": self.case.prompt}])
        self.assertEqual(body["max_tokens"], 64)
        self.assertEqual(body["temperature"], 0.0)
        self.assertIs(body["stream"], False)
        self.assertEqual(grade(self.case, result.text, latency_ms=result.latency_ms).status, "pass")

    def test_invalid_budget_and_model_rejected_before_io(self):
        invalid = [
            replace(self.experiment, model="@cf/moonshotai/kimi-k2.7-code"),
            replace(self.experiment, max_output_tokens=65),
            replace(self.experiment, max_output_tokens=True),
            replace(self.experiment, max_cases=4),
            replace(self.experiment, repetitions=2),
            replace(self.experiment, temperature=True),
            replace(self.experiment, cases=()),
        ]
        def never_send(*args):
            self.fail("transport must not run for invalid budget")
        for entry in invalid:
            with self.subTest(model=entry.model, max_output_tokens=entry.max_output_tokens,
                              max_cases=entry.max_cases, repetitions=entry.repetitions):
                with self.assertRaises(ContractError):
                    infer(entry, self.case, account_id=self.account_id,
                          api_token=self.api_token, transport=never_send)

    def test_case_and_account_guard(self):
        other = Case("unknown-001", "Hello", Assertion("exact", "OK"))
        for case, account in [
            (other, self.account_id),
            (replace(self.case, prompt="x" * 1001), self.account_id),
            (self.case, "not-hex"),
            (self.case, "https://example.test"),
        ]:
            with self.subTest(case_id=case.id, account=account):
                with self.assertRaises(ContractError):
                    infer(self.experiment, case, account_id=account,
                          api_token=self.api_token, transport=lambda *a: self.fail("called"))

    def test_token_validation_never_echoes_token(self):
        for token in ("", "contains space", "contains\nnewline"):
            with self.subTest(length=len(token)):
                with self.assertRaises(ProviderError) as ctx:
                    infer(self.experiment, self.case, account_id=self.account_id,
                          api_token=token, transport=lambda *a: self.fail("called"))
                self.assertEqual(ctx.exception.category, "auth")
                self.assertNotIn(token or "synthetic-test-token", str(ctx.exception))

    def test_bad_payload_is_sanitized_error_with_latency(self):
        for payload in (
            None, {}, {"success": False},
            {"success": True, "result": None},
            {"success": True, "result": {}},
            {"success": True, "result": {"response": ""}},
            {"success": True, "result": {"response": 123}},
        ):
            with self.subTest(payload=repr(payload)):
                clock = iter([3.0, 3.01])
                with self.assertRaises(ProviderError) as ctx:
                    infer(
                        self.experiment, self.case, account_id=self.account_id,
                        api_token=self.api_token, transport=lambda *args: payload,
                        clock=lambda: next(clock),
                    )
                self.assertEqual(ctx.exception.category, "invalid_response")
                self.assertEqual(ctx.exception.latency_ms, 9)

    def test_unexpected_transport_error_does_not_leak(self):
        marker = "synthetic-private-data"
        def broken_transport(*args):
            raise RuntimeError(marker)
        with self.assertRaises(ProviderError) as ctx:
            infer(self.experiment, self.case, account_id=self.account_id,
                  api_token=self.api_token, transport=broken_transport)
        self.assertEqual(ctx.exception.category, "provider")
        self.assertNotIn(marker, str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)

    def test_quota_error_sanitized_with_latency(self):
        clock = iter([1.0, 1.02])
        def quota(*args):
            raise ProviderError("quota")
        with self.assertRaises(ProviderError) as ctx:
            infer(self.experiment, self.case, account_id=self.account_id,
                  api_token=self.api_token, transport=quota,
                  clock=lambda: next(clock))
        self.assertEqual(ctx.exception.category, "quota")
        self.assertTrue(19 <= ctx.exception.latency_ms <= 20)

    def test_http_error_code_mapping(self):
        for status, code, category in [
            (401, None, "auth"),
            (403, None, "auth"),
            (403, 5035, "provider"),
            (429, 3036, "quota"),
            (429, 3040, "rate_limit"),
            (408, None, "timeout"),
            (504, None, "timeout"),
            (500, None, "provider"),
        ]:
            with self.subTest(status=status, code=code):
                body = json.dumps({"errors": [{"code": code, "message": "ignored"}]}).encode()
                error = urllib.error.HTTPError("https://example.invalid", status, "synthetic",
                                               {}, io.BytesIO(body))
                self.assertEqual(_http_error_category(error), category)

    def test_real_transport_shape_with_fake_opener(self):
        observed = []
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n):
                observed.append(("max_read", n))
                return json.dumps({"success": True, "result": {"response": "OK"}}).encode()
        class Opener:
            def open(self, request, timeout):
                observed.append(("request", request, timeout))
                return Response()
        with patch("llm_eval.providers.cloudflare.urllib.request.build_opener",
                   return_value=Opener()) as build:
            payload = _post_json("https://api.cloudflare.com/test", self.api_token,
                                 {"messages": [{"role": "user", "content": "OK"}]})
        self.assertEqual(payload["result"]["response"], "OK")
        self.assertEqual(observed[0][0], "request")
        request, timeout = observed[0][1:]
        self.assertEqual(timeout, 45)
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("Bearer " + self.api_token, request.get_header("Authorization"))
        self.assertEqual(observed[1], ("max_read", MAX_RESPONSE_BYTES + 1))
        self.assertIsInstance(build.call_args.args[0], _NoRedirects)

    def test_transport_rejects_oversized_successful_response(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n):
                return b"x" * (MAX_RESPONSE_BYTES + 1)
        class Opener:
            def open(self, request, timeout):
                return Response()
        with patch("llm_eval.providers.cloudflare.urllib.request.build_opener",
                   return_value=Opener()):
            with self.assertRaises(ProviderError) as ctx:
                _post_json("https://api.cloudflare.com/test", self.api_token, {})
        self.assertEqual(ctx.exception.category, "invalid_response")

    def test_transport_blocks_redirects(self):
        handler = _NoRedirects()
        self.assertIsNone(handler.redirect_request(None, None, 302, "moved", {}, "https://bad.test"))

    def test_transport_classifies_socket_timeout(self):
        class Opener:
            def open(self, request, timeout):
                raise urllib.error.URLError(socket.timeout("synthetic"))
        with patch("llm_eval.providers.cloudflare.urllib.request.build_opener",
                   return_value=Opener()):
            with self.assertRaises(ProviderError) as ctx:
                _post_json("https://api.cloudflare.com/test", self.api_token, {})
        self.assertEqual(ctx.exception.category, "timeout")

    def test_transport_classifies_rate_limits_without_exposing_body(self):
        marker = "synthetic-diagnostic-private"
        class Opener:
            def open(self, request, timeout):
                body = json.dumps({"errors": [{"code": 3036, "message": marker}]}).encode()
                raise urllib.error.HTTPError("https://api.cloudflare.com", 429,
                                             marker, {}, io.BytesIO(body))
        with patch("llm_eval.providers.cloudflare.urllib.request.build_opener",
                   return_value=Opener()):
            with self.assertRaises(ProviderError) as ctx:
                _post_json("https://api.cloudflare.com/test", self.api_token, {})
        self.assertEqual(ctx.exception.category, "quota")
        self.assertNotIn(marker, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
