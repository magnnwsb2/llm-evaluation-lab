"""Cloudflare Workers AI adapter — SDD-001 §5.1, §8 and §10.

This module does not make requests on import. CI tests inject fake responses;
only a future manual-only workflow may call the real transport.
"""

from __future__ import annotations

import http.client
import json
import math
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from ..contracts import (
    FREE_MODEL_ALLOWLIST,
    ACTIVE_INFERENCE_MODEL,
    MAX_CASES,
    MAX_OUTPUT_TOKENS,
    MAX_PROMPT_CHARS,
    MAX_REPETITIONS,
    PROVIDER,
    Case,
    ContractError,
    Experiment,
)
from ..scoring import ERROR_CATEGORIES

API_ORIGIN = "https://api.cloudflare.com"
REQUEST_TIMEOUT_SECONDS = 45
MAX_RESPONSE_BYTES = 64 * 1024
MAX_ERROR_BYTES = 4 * 1024
_ACCOUNT_ID = re.compile(r"[0-9a-fA-F]{32}\Z")


@dataclass(frozen=True, slots=True)
class InferenceResult:
    """Provider text and client-observed HTTP duration, not model-only latency."""

    text: str
    latency_ms: int


class ProviderError(RuntimeError):
    """Public, sanitized error type; never contains raw HTTP exceptions."""

    def __init__(self, category: str, *, latency_ms: int | None = None):
        if category not in ERROR_CATEGORIES:
            raise ValueError("Unsupported provider error category")
        self.category = category
        self.latency_ms = latency_ms
        super().__init__(f"Cloudflare request failed: {category}")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Never forward the authorization header to a redirected destination."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _validate_inputs(
    experiment: Experiment, case: Case, account_id: str, api_token: str
) -> None:
    """Defend against dataclasses constructed outside load_experiment()."""
    if type(experiment) is not Experiment or type(case) is not Case:
        raise ContractError("provider: validated Experiment and Case required")
    if experiment.provider != PROVIDER or (
        type(experiment.model) is not str or
        experiment.model not in FREE_MODEL_ALLOWLIST
    ):
        raise ContractError("provider: unsupported provider or model")
    if (
        type(experiment.max_cases) is not int or
        not 1 <= experiment.max_cases <= MAX_CASES or
        type(experiment.repetitions) is not int or
        experiment.repetitions != MAX_REPETITIONS or
        type(experiment.max_output_tokens) is not int or
        not 1 <= experiment.max_output_tokens <= MAX_OUTPUT_TOKENS
    ):
        raise ContractError("provider: experiment exceeds strict request budget")
    if (
        type(experiment.temperature) not in (int, float) or
        not math.isfinite(experiment.temperature) or
        not 0 <= experiment.temperature <= 1
    ):
        raise ContractError("provider: unsupported temperature")
    if (
        type(experiment.cases) is not tuple or
        not 1 <= len(experiment.cases) <= experiment.max_cases or
        case not in experiment.cases
    ):
        raise ContractError("provider: case not in validated experiment")
    if (
        type(case.prompt) is not str or
        not case.prompt.strip() or
        len(case.prompt) > MAX_PROMPT_CHARS
    ):
        raise ContractError("provider: prompt length invalid")
    if type(account_id) is not str or not _ACCOUNT_ID.fullmatch(account_id):
        raise ContractError("provider: invalid account identifier")
    if (
        type(api_token) is not str or
        not api_token or
        len(api_token) > 512 or
        any(char.isspace() for char in api_token)
    ):
        raise ProviderError("auth")


def _http_error_category(exc: urllib.error.HTTPError) -> str:
    """Inspect numeric Cloudflare error codes only; never reveal body text."""
    status = exc.code
    api_code: int | None = None
    if status in (403, 429):
        try:
            body = exc.read(MAX_ERROR_BYTES + 1)
            if len(body) <= MAX_ERROR_BYTES:
                data = json.loads(body)
                errors = data.get("errors", []) if type(data) is dict else []
                if type(errors) is list:
                    for item in errors:
                        if type(item) is dict and type(item.get("code")) is int:
                            api_code = item["code"]
                            break
        except (ValueError, UnicodeError, OSError):
            pass
    if api_code == 5035:
        return "provider"  # Paid-plan restricted model; no upgrade or fallback.
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "quota" if api_code == 3036 else "rate_limit"
    if status in (408, 504):
        return "timeout"
    return "provider"


def _post_json(
    url: str, api_token: str, body: dict[str, Any]
) -> Any:
    """One bounded HTTPS POST; never retry or accept redirects."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirects())
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ProviderError(_http_error_category(exc)) from None
    except urllib.error.URLError as exc:
        kind = "timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "network"
        raise ProviderError(kind) from None
    except (TimeoutError, socket.timeout):
        raise ProviderError("timeout") from None
    except (OSError, http.client.HTTPException):
        raise ProviderError("network") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderError("invalid_response")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise ProviderError("invalid_response") from None


def _response_text(payload: Any) -> str:
    """Extract one answer from either approved Cloudflare REST envelope.

    Legacy Llama returned result.response; Gemma can use chat-completion
    result.choices[0].message.content. Never accept ambiguous or empty data.
    """
    if type(payload) is not dict or payload.get("success") is not True:
        raise ProviderError("invalid_response")
    result = payload.get("result")
    if type(result) is not dict:
        raise ProviderError("invalid_response")
    has_response = "response" in result
    has_choices = "choices" in result
    if has_response == has_choices:
        raise ProviderError("invalid_response")
    if has_response:
        content = result["response"]
    else:
        choices = result["choices"]
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            raise ProviderError("invalid_response")
        message = choices[0].get("message")
        if type(message) is not dict:
            raise ProviderError("invalid_response")
        content = message.get("content")
    if type(content) is not str or not content.strip():
        raise ProviderError("invalid_response")
    return content

def infer(
    experiment: Experiment,
    case: Case,
    *,
    account_id: str,
    api_token: str,
    transport: Callable[[str, str, dict[str, Any]], Any] | None = None,
    clock: Callable[[], float] | None = None,
) -> InferenceResult:
    """Execute exactly one bounded call for a previously validated case.

    The optional transport and clock support **offline tests**. A manual runner
    must load the experiment with load_experiment before invoking this function.
    The token is never logged, returned or included in raised exception text.
    """
    _validate_inputs(experiment, case, account_id, api_token)
    url = f"{API_ORIGIN}/client/v4/accounts/{account_id}/ai/run/{experiment.model}"
    body = {
        "messages": [{"role": "user", "content": case.prompt}],
        "temperature": experiment.temperature,
        "stream": False,
    }
    # Gemma 4's documented chat API prefers max_completion_tokens.
    # Both forms are explicitly capped; never send both or rely on defaults.
    limit_key = (
        "max_completion_tokens"
        if experiment.model == ACTIVE_INFERENCE_MODEL else "max_tokens"
    )
    body[limit_key] = experiment.max_output_tokens
    if experiment.model == ACTIVE_INFERENCE_MODEL:
        # Official Gemma 4 guide uses this for ordinary short text replies.
        # Keep reasoning tokens from consuming the strict 64-token budget.
        body["chat_template_kwargs"] = {"enable_thinking": False}
    send = transport or _post_json
    timer = clock or time.perf_counter
    started = timer()

    def elapsed_ms() -> int:
        return max(0, int((timer() - started) * 1000))

    try:
        payload = send(url, api_token, body)
        text = _response_text(payload)
    except ProviderError as exc:
        raise ProviderError(exc.category, latency_ms=elapsed_ms()) from None
    except Exception:
        # A transport's unexpected exception may embed request headers or URLs.
        # Fail closed and never stringify or chain it into Actions logs.
        raise ProviderError("provider", latency_ms=elapsed_ms()) from None
    return InferenceResult(text=text, latency_ms=elapsed_ms())
