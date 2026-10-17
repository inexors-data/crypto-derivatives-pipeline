"""Shared HTTP client: retries with backoff and respect for exchange rate limits."""
import logging
import time

import requests

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, base_url: str, min_interval: float = 0.1, max_retries: int = 5, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval  # seconds between requests (simple client-side throttle)
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "crypto-derivatives-pipeline/1.0"
        self._last_call = 0.0

    def get(self, path: str, params: dict | None = None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(1, self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                delay = 2 ** attempt
                log.warning("%s: network error %s, retry in %ss", url, exc, delay)
                time.sleep(delay)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in RETRY_STATUSES:
                # Exchanges send Retry-After on 429; fall back to exponential backoff.
                delay = float(resp.headers.get("Retry-After", 2 ** attempt))
                log.warning("%s: HTTP %s, retry %s/%s in %ss", url, resp.status_code, attempt, self.max_retries, delay)
                time.sleep(delay)
                continue

            raise ApiError(f"{url} -> HTTP {resp.status_code}: {resp.text[:200]}")

        raise ApiError(f"{url}: gave up after {self.max_retries} attempts")
