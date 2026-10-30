"""Configurable AI provider layer.

Two providers ship with the MVP:

* GeminiProvider - a REAL call to Google's Gemini REST API (stdlib only, no SDK).
* DemoProvider   - clearly-labelled simulated text used when no API key is set.

Every result carries `mode` ("live" | "demo" | "error") so the UI can never pass a
simulation off as a live AI answer. To add another provider (OpenAI, Anthropic...),
subclass AIProvider and return it from get_provider().
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass

import config
import models

DEMO_BANNER = ("[DEMO MODE - simulated response. No AI model was called, so this text is a "
               "template, not real analysis.]")


@dataclass
class AIResult:
    text: str
    mode: str                 # models.MODE_LIVE | MODE_DEMO | MODE_ERROR
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.mode in (models.MODE_LIVE, models.MODE_DEMO)


class AIProvider(ABC):
    name = "base"
    is_live = False

    @abstractmethod
    def generate(self, system: str, prompt: str, history: list[dict] | None = None,
                 demo_hint: dict | None = None) -> AIResult:
        """history: [{"role": "owner"|"agent", "content": str}, ...] (oldest first)."""


# --------------------------------------------------------------------------- #
# Demo provider
# --------------------------------------------------------------------------- #
class DemoProvider(AIProvider):
    name = "demo"
    is_live = False

    def generate(self, system, prompt, history=None, demo_hint=None) -> AIResult:
        hint = demo_hint or {}
        agent = hint.get("agent_name", "Agent")
        role = hint.get("role", "specialist")
        outline = hint.get("outline") or ["Clarify the goal", "Gather the data", "Draft a plan", "Review with the owner"]
        needs = hint.get("needs") or ["Goal and timeframe", "Budget or constraints", "Any real data you can upload"]
        request = " ".join(str(prompt).split())[:300]
        lines = [
            DEMO_BANNER, "",
            f"{agent} ({role}) - understanding of your request:",
            f"> {request}", "",
            "Suggested approach (generic outline):",
            *[f"{i}. {step}" for i, step in enumerate(outline, 1)], "",
            "Information I would need for a real analysis:",
            *[f"- {n}" for n in needs], "",
            "Assumptions: none verified. Any numbers shown in demo mode are placeholders.",
            "To get real AI-generated work, add a GEMINI_API_KEY (see README, step 'Add your API key').",
        ]
        return AIResult("\n".join(lines), models.MODE_DEMO)


# --------------------------------------------------------------------------- #
# Gemini provider (live)
# --------------------------------------------------------------------------- #
class GeminiProvider(AIProvider):
    name = "gemini"
    is_live = True
    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str | None = None,
                 timeout: int = config.AI_TIMEOUT_SECONDS, max_retries: int = config.AI_MAX_RETRIES,
                 sleep=time.sleep):
        self._api_key = api_key      # never logged, never displayed
        self.model = model or config.gemini_model()
        self.timeout = timeout
        self.max_retries = max(0, min(int(max_retries), 3))
        self._sleep = sleep

    # -- request building ---------------------------------------------------
    def _body(self, system: str, prompt: str, history: list[dict] | None) -> dict:
        contents = []
        for m in (history or [])[-12:]:
            role = "user" if m.get("role") == "owner" else "model"
            text = str(m.get("content", "")).strip()
            if text:
                contents.append({"role": role, "parts": [{"text": text[:6000]}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.6, "maxOutputTokens": 2048},
        }

    @staticmethod
    def _friendly_http_error(code: int) -> str:
        return {
            400: "The AI service rejected the request (400). Check that GEMINI_API_KEY is valid and GEMINI_MODEL exists.",
            401: "The AI service rejected the API key (401).",
            403: "The AI service denied access (403). The API key may be invalid, restricted or not enabled.",
            404: "The configured Gemini model was not found (404). Check GEMINI_MODEL.",
            429: "The AI service rate limit was reached (429). Wait a minute and try again.",
        }.get(code, f"The AI service returned an error (HTTP {code}).")

    # -- main call ----------------------------------------------------------
    def generate(self, system, prompt, history=None, demo_hint=None) -> AIResult:
        url = self.ENDPOINT.format(model=self.model)
        payload = json.dumps(self._body(system, prompt, history)).encode("utf-8")
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._api_key}
        last_error = "Unknown error"
        attempts = self.max_retries + 1          # bounded: never an infinite retry loop
        for attempt in range(attempts):
            try:
                req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return self._parse(data)
            except urllib.error.HTTPError as exc:
                last_error = self._friendly_http_error(exc.code)
                retryable = exc.code in (429, 500, 502, 503, 504)
                if not retryable:
                    break
            except (socket.timeout, TimeoutError):
                last_error = f"The AI service timed out after {self.timeout}s."
            except urllib.error.URLError as exc:
                reason = getattr(exc, "reason", exc)
                if isinstance(reason, (socket.timeout, TimeoutError)):
                    last_error = f"The AI service timed out after {self.timeout}s."
                else:
                    last_error = "Could not reach the AI service. Check your internet connection."
            except (ValueError, KeyError) as exc:
                last_error = f"Unreadable response from the AI service ({type(exc).__name__})."
                break
            except Exception as exc:  # never leak secrets from unexpected errors
                last_error = config.redact(f"Unexpected AI error: {type(exc).__name__}")
                break
            if attempt < attempts - 1:
                self._sleep(min(2 ** attempt * 2, 10))
        return AIResult("", models.MODE_ERROR, config.redact(last_error))

    @staticmethod
    def _parse(data: dict) -> AIResult:
        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            return AIResult("", models.MODE_ERROR,
                            f"The AI service blocked this request ({feedback['blockReason']}). Try rewording it.")
        candidates = data.get("candidates") or []
        if not candidates:
            return AIResult("", models.MODE_ERROR, "The AI service returned no answer.")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            reason = candidates[0].get("finishReason", "unknown")
            return AIResult("", models.MODE_ERROR, f"The AI service returned an empty answer (reason: {reason}).")
        return AIResult(text, models.MODE_LIVE)


# --------------------------------------------------------------------------- #
# Factory + status
# --------------------------------------------------------------------------- #
def get_provider() -> AIProvider:
    key = config.gemini_api_key()
    if key and not config.force_demo_mode():
        return GeminiProvider(key)
    return DemoProvider()


def provider_status() -> dict:
    """Safe-to-display status (never includes the key itself)."""
    key = bool(config.gemini_api_key())
    forced = config.force_demo_mode()
    live = key and not forced
    return {
        "live": live,
        "key_present": key,
        "forced_demo": forced,
        "provider": "Gemini" if live else "Demo (simulated)",
        "model": config.gemini_model() if live else "-",
    }
