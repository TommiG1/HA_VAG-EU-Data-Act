"""Mocked HTTP tests for api.py (no live portal, no Home Assistant)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from _loader import load_modules  # noqa: E402


class _FakeResponse:
    def __init__(
        self,
        status: int,
        body: str = "",
        url: str = "https://example.test/",
        history: list | None = None,
    ):
        self.status = status
        self._body = body
        self.url = url
        self.history = history or []

    async def text(self) -> str:
        return self._body

    async def read(self) -> bytes:
        return self._body.encode()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.cookie_jar = []

    def post(self, *args, **kwargs):
        return self._responses.pop(0)

    async def close(self):
        return None


def _client(api, session, brand, logged_in: bool = True):
    client = api.EudaApiClient(session, "test@example.com", "secret", brand)
    client._logged_in = logged_in
    return client


async def _run(label: str, coro, failures: list[str]) -> None:
    try:
        got = await coro
        print(f"  [PASS] {label}: {got!r}")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] {label}: {type(err).__name__}: {err}")
        failures.append(label)


async def main() -> int:
    mods = load_modules("const", "brands", "api")
    api = mods["api"]
    const = mods["const"]
    brand = mods["brands"].get_brand("cupra")
    failures: list[str] = []

    print("async_list_datasets:")
    url = f"{const.BASE_URL}{const.LIST_PATH.format(vin='WVWZZZTESTVIN0001', identifier='abc123')}"

    async def _get_404(self, req_url, **kwargs):
        assert req_url == url
        return _FakeResponse(404, url=req_url)

    session = _FakeSession([])
    client = _client(api, session, brand)
    client._get = _get_404.__get__(client, api.EudaApiClient)
    await _run("HTTP 404 -> empty list", client.async_list_datasets("WVWZZZTESTVIN0001", "abc123"), failures)

    payload = [{"name": "20260101120000_WVWZZZTESTVIN0001.zip", "createdOn": "2026-01-01T12:00:00Z"}]

    async def _get_200(self, req_url, **kwargs):
        return _FakeResponse(200, json.dumps(payload), url=req_url)

    session2 = _FakeSession([])
    client2 = _client(api, session2, brand)
    client2._get = _get_200.__get__(client2, api.EudaApiClient)
    await _run("HTTP 200 -> parsed list", client2.async_list_datasets("WVWZZZTESTVIN0001", "abc123"), failures)

    print("content filtering:")
    listing = [
        {"name": "20260101120000_WVWZZZTESTVIN0001_no_content_found.zip"},
        {"name": "20260101121500_WVWZZZTESTVIN0001.zip"},
    ]
    content = [
        e
        for e in listing
        if e.get("name") and not e["name"].endswith(const.NO_CONTENT_SUFFIX)
    ]
    ok = len(content) == 1 and content[0]["name"].endswith(".zip")
    print(f"  [{'PASS' if ok else 'FAIL'}] skip no_content zip: {content!r}")
    if not ok:
        failures.append("content filtering")

    print("login finish / callbacklogin:")
    portal = const.BASE_URL.rstrip("/")
    callback = _FakeResponse(302, url=f"{portal}/services/callbacklogin?code=x")
    landing_ok = _FakeResponse(
        404,
        body="CMS missing",
        url=f"{portal}/ch/de.html",
        history=[callback],
    )
    check_cb = api._passed_portal_callback(landing_ok)
    print(f"  [{'PASS' if check_cb else 'FAIL'}] callback via history: {check_cb}")
    if not check_cb:
        failures.append("callback via history")

    landing_fail = _FakeResponse(500, body="boom", url=f"{portal}/", history=[])
    check_no = not api._passed_portal_callback(landing_fail)
    print(f"  [{'PASS' if check_no else 'FAIL'}] no callback without hop: {check_no}")
    if not check_no:
        failures.append("no callback without hop")

    session_login = _FakeSession([])
    client_login = _client(api, session_login, brand, logged_in=False)

    async def _probe_200(self, req_url, **kwargs):
        return _FakeResponse(200, "[]", url=req_url)

    client_login._get = _probe_200.__get__(client_login, api.EudaApiClient)
    try:
        await client_login._finish_login(landing_ok)
        print("  [PASS] finish_login ignores landing 404 after callback")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] finish_login ignores landing 404: {type(err).__name__}: {err}")
        failures.append("finish_login landing 404")

    try:
        await client_login._finish_login(landing_fail)
        print("  [FAIL] finish_login should reject 500 without callback")
        failures.append("finish_login reject without callback")
    except api.AuthError:
        print("  [FAIL] finish_login 500 must not be AuthError")
        failures.append("finish_login reject without callback")
    except api.ApiError as err:
        if err.status == 500:
            print("  [PASS] finish_login 500 without callback is retryable ApiError")
        else:
            print(f"  [FAIL] finish_login 500 status={err.status}")
            failures.append("finish_login reject without callback")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected: {type(err).__name__}: {err}")
        failures.append("finish_login reject without callback")

    landing_429 = _FakeResponse(429, body="slow down", url=f"{portal}/", history=[])
    try:
        await client_login._finish_login(landing_429)
        print("  [FAIL] finish_login should reject 429 without callback")
        failures.append("finish_login 429")
    except api.AuthError:
        print("  [FAIL] finish_login 429 must not be AuthError")
        failures.append("finish_login 429")
    except api.ApiError as err:
        if err.status == 429:
            print("  [PASS] finish_login 429 without callback is retryable ApiError")
        else:
            print(f"  [FAIL] finish_login 429 status={err.status}")
            failures.append("finish_login 429")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected: {type(err).__name__}: {err}")
        failures.append("finish_login 429")

    landing_401 = _FakeResponse(401, body="unauthorized", url=f"{portal}/", history=[])
    try:
        await client_login._finish_login(landing_401)
        print("  [FAIL] finish_login should reject 401 without callback")
        failures.append("finish_login 401")
    except api.AuthError as err:
        if err.status == 401:
            print("  [PASS] finish_login 401 without callback is AuthError")
        else:
            print(f"  [FAIL] finish_login 401 status={err.status}")
            failures.append("finish_login 401")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected: {type(err).__name__}: {err}")
        failures.append("finish_login 401")

    terms_html = (
        '<form action="/signin-service/v1/client@apps/terms-and-conditions" method="POST">'
        '<input name="_csrf" value="csrf1">'
        '<input name="relayState" value="rs1">'
        '<input name="hmac" value="hm1">'
        '<input name="countryOfResidence" value="ES">'
        "</form>"
    )
    terms = _FakeResponse(
        200,
        body=terms_html,
        url=(
            "https://identity.vwgroup.io/signin-service/v1/client@apps/"
            "terms-and-conditions?updated=termsofuse"
        ),
    )
    session_terms = _FakeSession([landing_ok])
    client_terms = _client(api, session_terms, brand, logged_in=False)
    client_terms._get = _probe_200.__get__(client_terms, api.EudaApiClient)
    try:
        await client_terms._finish_login(terms)
        print("  [PASS] finish_login auto-accepts terms interstitial")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] finish_login terms auto-accept: {type(err).__name__}: {err}")
        failures.append("finish_login terms auto-accept")

    terms_empty = _FakeResponse(
        200,
        body="<form></form>",
        url="https://identity.vwgroup.io/terms-and-conditions?updated=dataprivacy",
    )
    try:
        await client_login._finish_login(terms_empty)
        print("  [FAIL] finish_login should reject terms form without fields")
        failures.append("finish_login terms missing fields")
    except api.AuthError as err:
        ok_terms = "terms" in str(err).lower()
        print(f"  [{'PASS' if ok_terms else 'FAIL'}] terms missing fields: {err}")
        if not ok_terms:
            failures.append("finish_login terms missing fields")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected terms missing fields: {type(err).__name__}: {err}")
        failures.append("finish_login terms missing fields")

    session_terms_loop = _FakeSession([terms])
    client_terms_loop = _client(api, session_terms_loop, brand, logged_in=False)
    try:
        await client_terms_loop._finish_login(terms)
        print("  [FAIL] finish_login should reject repeated terms interstitial")
        failures.append("finish_login terms loop")
    except api.AuthError as err:
        ok_loop = "after submission" in str(err).lower()
        print(f"  [{'PASS' if ok_loop else 'FAIL'}] terms loop guard: {err}")
        if not ok_loop:
            failures.append("finish_login terms loop")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected terms loop: {type(err).__name__}: {err}")
        failures.append("finish_login terms loop")

    print()
    if failures:
        print(f"FAILED: {len(failures)} -> {failures}")
        return 1
    print("ALL API MOCK TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
