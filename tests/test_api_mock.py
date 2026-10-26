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
        headers: dict | None = None,
        cookies: dict | None = None,
    ):
        self.status = status
        self._body = body
        self.url = url
        self.history = history or []
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.released = False

    async def text(self) -> str:
        return self._body

    async def read(self) -> bytes:
        return self._body.encode()

    def release(self) -> None:
        self.released = True

    def __await__(self):
        async def _response():
            return self

        return _response().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.cookie_jar = []
        self.requests = []

    def post(self, *args, **kwargs):
        self.requests.append(("POST", args, kwargs))
        return self._responses.pop(0)

    def get(self, *args, **kwargs):
        self.requests.append(("GET", args, kwargs))
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

    first_redirect = _FakeResponse(
        302,
        url="https://identity.vwgroup.io/login/authenticate",
        headers={"Location": f"{portal}/services/callbacklogin?code=x"},
    )
    callback_redirect = _FakeResponse(
        302,
        url=f"{portal}/services/callbacklogin?code=x",
        headers={"Location": f"{portal}/content/euda/de/de/user.html"},
        cookies={"access_token": "token"},
    )
    redirect_session = _FakeSession([first_redirect, callback_redirect])
    redirect_client = _client(api, redirect_session, brand, logged_in=False)
    stopped = await redirect_client._post_login_form(
        "https://identity.vwgroup.io/login/authenticate",
        data={"password": "secret"},
        referer="https://identity.vwgroup.io/signin",
    )
    stopped_ok = (
        stopped is callback_redirect
        and first_redirect.released
        and len(redirect_session.requests) == 2
        and redirect_session.requests[1][0] == "GET"
        and redirect_session.requests[1][1][0]
        == f"{portal}/services/callbacklogin?code=x"
        and redirect_session.requests[1][2]["allow_redirects"] is False
    )
    print(
        f"  [{'PASS' if stopped_ok else 'FAIL'}] "
        "stop on callback redirect without fetching CMS page"
    )
    if not stopped_ok:
        failures.append("stop on callback redirect")

    try:
        await client_login._finish_login(callback_redirect)
        print("  [PASS] finish_login accepts callback access_token cookie")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] callback access_token: {type(err).__name__}: {err}")
        failures.append("callback access_token")

    callback_without_token = _FakeResponse(
        302,
        url=f"{portal}/services/callbacklogin?code=x",
        headers={"Location": f"{portal}/content/euda/de/de/user.html"},
    )
    try:
        await client_login._finish_login(callback_without_token)
        print("  [FAIL] finish_login should reject callback without access_token")
        failures.append("callback missing access_token")
    except api.AuthError as err:
        missing_token = "access_token" in str(err)
        print(
            f"  [{'PASS' if missing_token else 'FAIL'}] "
            f"callback missing access_token: {err}"
        )
        if not missing_token:
            failures.append("callback missing access_token")

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
    session_terms = _FakeSession([callback_redirect])
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

    marketing_url = (
        "https://identity.vwgroup.io/signin-service/v1/consent/marketing/user/client"
        "?callback=https%3A%2F%2Fidentity.vwgroup.io%2Foidc%2Fv1%2Foauth%2Fclient%2Fcallback"
        "%3Fuser_id%3Du1%26scopes%3Dopenid%20cars&hmac=abc"
    )
    marketing = _FakeResponse(200, body="please consent", url=marketing_url)
    marketing_hop = _FakeResponse(
        302,
        url=(
            "https://identity.vwgroup.io/oidc/v1/oauth/client/callback"
            "?user_id=u1&scopes=openid+cars"
        ),
        headers={"Location": f"{portal}/services/callbacklogin?code=x"},
    )
    session_marketing = _FakeSession([marketing_hop, callback_redirect])
    client_marketing = _client(api, session_marketing, brand, logged_in=False)
    try:
        await client_marketing._finish_login(marketing)
        marketing_get = session_marketing.requests[0]
        skipped = (
            marketing_get[0] == "GET"
            and marketing_get[1][0].startswith(
                "https://identity.vwgroup.io/oidc/v1/oauth/client/callback?"
            )
            and "scopes=openid+cars" in marketing_get[1][0]
            and session_marketing.requests[1][1][0]
            == f"{portal}/services/callbacklogin?code=x"
        )
        print(
            f"  [{'PASS' if skipped else 'FAIL'}] "
            "finish_login skips marketing consent via callback"
        )
        if not skipped:
            failures.append("finish_login marketing skip")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] finish_login marketing skip: {type(err).__name__}: {err}")
        failures.append("finish_login marketing skip")

    marketing_again = _FakeResponse(200, body="please consent", url=marketing_url)
    session_marketing_loop = _FakeSession([marketing_again])
    client_marketing_loop = _client(api, session_marketing_loop, brand, logged_in=False)
    try:
        await client_marketing_loop._finish_login(marketing)
        print("  [FAIL] finish_login should reject a repeated marketing page")
        failures.append("finish_login marketing loop")
    except api.AuthError as err:
        ok_marketing_loop = "after it was skipped" in str(err)
        print(f"  [{'PASS' if ok_marketing_loop else 'FAIL'}] marketing loop guard: {err}")
        if not ok_marketing_loop:
            failures.append("finish_login marketing loop")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected marketing loop: {type(err).__name__}: {err}")
        failures.append("finish_login marketing loop")

    marketing_open = _FakeResponse(
        200,
        url="https://identity.vwgroup.io/signin-service/v1/consent/marketing/user/client",
    )
    try:
        await client_login._finish_login(marketing_open)
        print("  [FAIL] finish_login should reject marketing page without callback")
        failures.append("finish_login marketing missing callback")
    except api.AuthError as err:
        ok_missing = "without a continuation" in str(err)
        print(f"  [{'PASS' if ok_missing else 'FAIL'}] marketing missing callback: {err}")
        if not ok_missing:
            failures.append("finish_login marketing missing callback")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected marketing missing callback: {type(err).__name__}: {err}")
        failures.append("finish_login marketing missing callback")

    marketing_evil = _FakeResponse(
        200,
        url=(
            "https://identity.vwgroup.io/signin-service/v1/consent/marketing/user/client"
            "?callback=https%3A%2F%2Fevil.example%2Fphish"
        ),
    )
    try:
        await client_login._finish_login(marketing_evil)
        print("  [FAIL] finish_login should reject an off-host marketing callback")
        failures.append("finish_login marketing off-host")
    except api.AuthError as err:
        ok_host = "unexpected" in str(err)
        print(f"  [{'PASS' if ok_host else 'FAIL'}] marketing off-host callback: {err}")
        if not ok_host:
            failures.append("finish_login marketing off-host")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected marketing off-host: {type(err).__name__}: {err}")
        failures.append("finish_login marketing off-host")

    auth0_login_url = (
        "https://identity.vwgroup.io/u/login?state=hKFo2SBteststatevalue"
    )
    auth0_html = (
        '<form method="POST" data-form-primary="true">'
        '<input type="hidden" name="state" value="hKFo2SBteststatevalue">'
        '<input name="username" value="">'
        '<input name="password" value="">'
        '<button type="submit" name="action" value="default">Continue</button>'
        "</form>"
    )
    auth0_authorize = _FakeResponse(200, body=auth0_html, url=auth0_login_url)
    auth0_post = _FakeResponse(
        302,
        url=auth0_login_url,
        headers={"Location": f"{portal}/services/callbacklogin?code=auth0"},
    )
    auth0_callback = _FakeResponse(
        302,
        url=f"{portal}/services/callbacklogin?code=auth0",
        headers={"Location": f"{portal}/content/euda/de/de/user.html"},
        cookies={"access_token": "token"},
    )
    auth0_session = _FakeSession([auth0_authorize, auth0_post, auth0_callback])
    auth0_client = _client(api, auth0_session, brand, logged_in=False)
    try:
        await auth0_client.async_login()
        post_req = auth0_session.requests[1]
        posted = post_req[2]["data"]
        auth0_ok = (
            post_req[0] == "POST"
            and post_req[1][0] == auth0_login_url
            and posted.get("username") == "test@example.com"
            and posted.get("password") == "secret"
            and posted.get("state") == "hKFo2SBteststatevalue"
            and posted.get("action") == "default"
            and auth0_client._logged_in is True
        )
        print(f"  [{'PASS' if auth0_ok else 'FAIL'}] Auth0 /u/login single-step login")
        if not auth0_ok:
            failures.append("auth0 login")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] Auth0 login: {type(err).__name__}: {err}")
        failures.append("auth0 login")

    auth0_bad = _FakeResponse(
        400,
        body=(
            '<div id="error-element-password" '
            'data-error-code="wrong-email-or-password">bad</div>'
        ),
        url=auth0_login_url,
    )
    try:
        await client_login._finish_login(auth0_bad)
        print("  [FAIL] finish_login should reject Auth0 wrong password")
        failures.append("auth0 wrong password")
    except api.AuthError as err:
        ok_bad = "password" in str(err).lower() and err.status == 400
        print(f"  [{'PASS' if ok_bad else 'FAIL'}] Auth0 wrong password: {err}")
        if not ok_bad:
            failures.append("auth0 wrong password")
    except Exception as err:  # noqa: BLE001
        print(f"  [FAIL] unexpected Auth0 wrong password: {type(err).__name__}: {err}")
        failures.append("auth0 wrong password")

    print()
    if failures:
        print(f"FAILED: {len(failures)} -> {failures}")
        return 1
    print("ALL API MOCK TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
