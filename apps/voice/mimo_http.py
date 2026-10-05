"""Bounded MiMo HTTP/SSE transport with credential-free errors."""
import json
import time
from urllib.parse import urlsplit

import requests


class MiMoError(RuntimeError):
    def __init__(self, kind, status=0, retry_after=0):
        self.kind = kind
        self.status = status
        self.retry_after = min(2.0, max(0.0, retry_after))
        super().__init__("MiMo %s%s" % (kind, " HTTP %s" % status if status else ""))

    @property
    def retryable(self):
        return self.kind in ("timeout", "network") or self.status in (429, 500, 502, 503, 504)


class MiMoHTTP:
    MAX_BODY = 12 * 1024 * 1024
    MAX_EVENT = 2 * 1024 * 1024

    def __init__(self, api_key=None, url=None, session=None):
        from config import MIMO_API_KEY, MIMO_API_URL
        self.api_key = MIMO_API_KEY if api_key is None else api_key
        self.url = MIMO_API_URL if url is None else url
        parts = urlsplit(self.url)
        if (parts.scheme != "https" or parts.hostname != "api.xiaomimimo.com" or
                parts.username or parts.password or parts.query or parts.fragment or
                parts.port not in (None, 443) or parts.path != "/v1/chat/completions"):
            raise MiMoError("invalid_endpoint")
        self.session = session or requests.Session()

    def close(self):
        self.session.close()

    def responses(self, payload, budget=30.0):
        """Yield JSON events. Budget is checked per byte to stop trickle streams.

        A pending connect/read can exceed the budget by at most its respective
        5s/10s timeout; the caller must not layer unlimited retries on top.
        """
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise MiMoError("missing_key")
        deadline = time.monotonic() + budget
        response = None
        try:
            response = self.session.post(
                self.url, headers={"Authorization": "Bearer " + self.api_key,
                                   "Content-Type": "application/json"},
                json=payload, stream=True,
                timeout=(min(5, max(1, budget / 3)),
                         min(10, max(1, budget / 2))),
                allow_redirects=False,
            )
            if response.status_code != 200:
                try:
                    delay = float(response.headers.get("Retry-After", 0))
                except (TypeError, ValueError):
                    delay = 0
                raise MiMoError("http", response.status_code, delay)

            streaming = bool(payload.get("stream"))
            if streaming and "text/event-stream" not in response.headers.get("Content-Type", "").lower():
                raise MiMoError("not_streaming")
            body = bytearray()
            data_lines = []
            event_size = 0
            count = 0
            # Parse bounded chunks instead of iterating byte by byte on RK3568.
            # The 10-second socket read timeout remains the upper bound while a
            # peer is trickling an incomplete line.
            for chunk in response.iter_content(chunk_size=1024):
                if time.monotonic() > deadline:
                    raise MiMoError("timeout")
                if not chunk:
                    continue
                count += len(chunk)
                if count > self.MAX_BODY:
                    raise MiMoError("response_too_large")
                body.extend(chunk)
                if not streaming:
                    continue
                while b"\n" in body:
                    line, remainder = body.split(b"\n", 1)
                    body = bytearray(remainder)
                    line = line.rstrip(b"\r")
                    if line.startswith(b"data:"):
                        data = line[5:].lstrip(b" ")
                        data_lines.append(data)
                        event_size += len(data)
                    elif not line and data_lines:
                        raw = b"\n".join(data_lines)
                        data_lines.clear()
                        event_size = 0
                        if raw == b"[DONE]":
                            yield {"_done": True}
                            return
                        yield self._json(raw)
                if len(body) + event_size > self.MAX_EVENT:
                    raise MiMoError("event_too_large")
            if time.monotonic() > deadline:
                raise MiMoError("timeout")
            if not streaming:
                yield self._json(body)
            elif body or data_lines:
                raise MiMoError("truncated_stream")
        except requests.Timeout:
            raise MiMoError("timeout") from None
        except requests.RequestException:
            raise MiMoError("network") from None
        finally:
            if response is not None:
                response.close()

    @staticmethod
    def _json(raw):
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise MiMoError("invalid_json") from None
        if not isinstance(value, dict) or value.get("error"):
            raise MiMoError("invalid_response")
        return value

    def request(self, payload, budget=30.0):
        events = self.responses(payload, budget)
        try:
            return next(events)
        finally:
            events.close()


def first_choice(data, allow_tools=False):
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise MiMoError("invalid_response")
    choice = choices[0]
    valid = (None, "stop", "tool_calls") if allow_tools else (None, "stop")
    if choice.get("finish_reason") not in valid:
        raise MiMoError("incomplete_response")
    return choice


def retry_pause(error, attempt):
    time.sleep(max(error.retry_after, min(0.5 * (2 ** attempt), 2.0)))
