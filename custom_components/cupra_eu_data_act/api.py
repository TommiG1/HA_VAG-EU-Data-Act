"""Client for the VW Group EU Data Act portal (OIDC login + data delivery)."""
from __future__ import annotations

import io
import json
import logging
import re
import uuid
import zipfile
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import aiohttp

from .brands import BrandConfig
from .const import (
    BASE_URL,
    CALLBACK_LOGIN_PATH,
    IDENTITY_BASE,
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
    DOWNLOAD_PATH,
    LIST_PATH,
    METADATA_PATH,
    NO_CONTENT_SUFFIX,
    OIDC_AUTHORIZE_URL,
    OIDC_REDIRECT_URI,
    OIDC_SCOPE,
    LOGIN_TRANSIENT_HTTP_STATUSES,
    RELATION_PATH,
    USER_AGENT,
    VEHICLES_PATH,
)

_LOGGER = logging.getLogger(__name__)
_LOGIN_REDIRECT_STATUSES = frozenset({301, 302, 303})
_MAX_LOGIN_REDIRECTS = 10


class ApiError(Exception):
    """Generic API failure.

    Carries the HTTP ``status`` when the failure came from an HTTP response so
    callers can branch on it (e.g. retry 5xx, surface 400 as "delivery not
    ready") without grepping the message. ``None`` for non-HTTP failures
    (connection errors, bad JSON, …).
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AuthError(ApiError):
    """Authentication failed or session expired."""


def _raise_login_failure(message: str, *, status: int | None = None) -> None:
    """Raise AuthError, unless the HTTP status is a transient portal/IdP failure.

    HTTP 429/404/5xx during login is an outage, not invalid credentials.
    Raising AuthError would make Home Assistant prompt for reauth.
    """
    if status in LOGIN_TRANSIENT_HTTP_STATUSES:
        _LOGGER.warning("Login hit transient HTTP %s: %s", status, message)
        raise ApiError(message, status=status)
    raise AuthError(message, status=status)


class _FormParser(HTMLParser):
    """Extract the first <form> action and all hidden/input fields."""

    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._in_form = False
        self._done = False  # only capture the first form

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        a = dict(attrs)
        if tag == "form" and self.action is None:
            self.action = a.get("action")
            self._in_form = True
        elif tag == "input" and self._in_form:
            name = a.get("name")
            if name:
                self.fields[name] = a.get("value") or ""
        elif tag == "button" and self._in_form:
            # Auth0 Universal Login submits ``action=default`` via the
            # primary submit button rather than a hidden input.
            name = a.get("name")
            if name and (a.get("type") or "submit") == "submit":
                self.fields[name] = a.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._in_form:
            self._in_form = False
            self._done = True


def _parse_form(html: str) -> _FormParser:
    p = _FormParser()
    p.feed(html)
    return p


def _extract_template_model(html: str) -> dict:
    """Extract the VW identity ``templateModel`` JSON embedded in the page.

    The signin/authenticate pages carry their form state (hmac, relayState,
    prefilled email, postAction, error) in a JS object rather than HTML inputs:

        window._IDK = { templateModel: { ... }, csrf_token: '...' }
    """
    idx = html.find("templateModel")
    if idx == -1:
        return {}
    brace = html.find("{", idx)
    if brace == -1:
        return {}
    depth = 0
    for i in range(brace, len(html)):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[brace : i + 1])
                except ValueError:
                    return {}
    return {}


def _extract_csrf(html: str) -> str | None:
    """Pull the csrf_token out of the identity page's JS."""
    m = re.search(r"csrf_token\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
    return m.group(1) if m else None


def _login_fields(html: str) -> tuple[dict[str, str], str | None]:
    """Collect the fields needed to POST a VW identity login step.

    Merges HTML hidden inputs with the JS templateModel/csrf so it works
    whether the page renders inputs server-side (email step) or via JS
    (password step). Returns (fields, form_action)."""
    form = _parse_form(html)
    fields: dict[str, str] = dict(form.fields)
    model = _extract_template_model(html)
    if model:
        for key in ("hmac", "relayState"):
            if model.get(key):
                fields[key] = model[key]
        email = (model.get("emailPasswordForm") or {}).get("email")
        if email:
            fields.setdefault("email", email)
    csrf = _extract_csrf(html)
    if csrf:
        fields.setdefault("_csrf", csrf)
    return fields, form.action


def _login_error(html: str) -> str | None:
    """Return a human-readable login error from the page, if present."""
    model = _extract_template_model(html)
    err = model.get("error") or model.get("errorCode")
    if isinstance(err, dict):
        return err.get("text") or err.get("errorCode") or str(err)
    if err:
        return str(err)
    # Auth0 Universal Login encodes failures as data-error-code attributes.
    m = re.search(r'data-error-code=["\']([^"\']+)["\']', html)
    if not m:
        return None
    code = m.group(1).strip()
    if code in {"wrong-email-or-password", "wrong-email-credentials"}:
        return "Login failed - check email and password"
    return code.replace("-", " ") if code else None


def _is_auth0_login(url: str, fields: dict[str, str]) -> bool:
    """Return whether the IdP served Auth0 Universal Login (``/u/login``).

    CUPRA/SEAT currently land here; other brands still use the classic
    signin-service pages with ``hmac`` / ``_csrf`` / ``relayState``.
    """
    if "/u/login" in urlparse(url).path:
        return True
    return (
        "username" in fields
        and "password" in fields
        and "state" in fields
        and "hmac" not in fields
    )


def _accept_language(language: str, country: str | None = None) -> str:
    """Build an Accept-Language header from ISO language/country codes."""
    if len(language) == 2:
        region = (country or language).upper()
        return f"{language}-{region},{language};q=0.9,en;q=0.8"
    return "en-US,en;q=0.9"


def _login_headers(
    country: str,
    language: str,
    referer: str | None = None,
) -> dict[str, str]:
    """Browser-like headers for the VW identity login flow."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": _accept_language(language, country),
        "Cache-Control": "max-age=0",
    }
    if referer:
        headers["Referer"] = referer
        parsed = urlparse(referer)
        headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    return headers


def _marketing_consent_callback(url: str) -> str | None:
    """Return the continuation URL from the classic marketing-consent page.

    Older IdP flows insert ``/consent/marketing/`` after login. Consent is not
    required; the ``callback`` query parameter is the next hop (GET). Returns
    None when ``url`` is not that page.
    """
    parsed = urlparse(url)
    if "/consent/marketing/" not in parsed.path:
        return None
    raw = parse_qs(parsed.query).get("callback", [""])[0]
    if not raw:
        raise AuthError(
            "Login interrupted: the identity provider showed a marketing "
            "consent page without a continuation URL"
        )
    target = urlparse(urljoin(url, raw))
    allowed = {urlparse(BASE_URL).netloc, urlparse(IDENTITY_BASE).netloc}
    if target.scheme != "https" or target.netloc not in allowed:
        raise AuthError(
            "Login interrupted: the marketing consent page has an unexpected "
            "continuation URL"
        )
    query = urlencode(parse_qs(target.query, keep_blank_values=True), doseq=True)
    return urlunparse(target._replace(query=query))


def _marketing_consent_v2_skip(url: str) -> tuple[str, dict[str, str]] | None:
    """Return (skip_url, form fields) for the v2 SPA marketing-consent page.

    Newer flows land on ``/v2/login/ui/marketing-consent`` with ``relayState``
    and ``state`` query parameters (no ``callback``). The SPA skips by POSTing
    those fields to ``…/marketing-consent/skip``. Returns None when ``url`` is
    not that page.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if "/login/ui/marketing-consent" not in path:
        return None
    if path.endswith("/skip") or path.endswith("/accept"):
        return None
    if parsed.scheme != "https" or parsed.netloc != urlparse(IDENTITY_BASE).netloc:
        raise AuthError(
            "Login interrupted: the marketing consent page has an unexpected host"
        )
    qs = parse_qs(parsed.query)
    relay = (qs.get("relayState") or [""])[0]
    state = (qs.get("state") or [""])[0]
    if not relay or not state:
        raise AuthError(
            "Login interrupted: the identity provider showed a marketing "
            "consent page without relayState/state"
        )
    skip_url = urlunparse(parsed._replace(path=f"{path}/skip", query="", fragment=""))
    return skip_url, {"relayState": relay, "state": state}


def _is_portal_callback(url: str) -> bool:
    """Return whether URL is the portal's OIDC callback endpoint."""
    parsed = urlparse(url)
    return (
        parsed.netloc == urlparse(BASE_URL).netloc
        and parsed.path.startswith(CALLBACK_LOGIN_PATH)
    )


def _passed_portal_callback(resp) -> bool:
    """Return True if the redirect chain went through the portal login callback.

    ``/services/callbacklogin`` exchanges the OIDC code and sets the portal
    session cookies. Reaching it means authentication completed, regardless of
    what the final localized CMS landing page returns (some locales 4xx/5xx
    there even after a successful login).
    """
    history = getattr(resp, "history", ()) or ()
    for hop in list(history) + [resp]:
        url = getattr(hop, "url", None)
        if url is not None and _is_portal_callback(str(url)):
            return True
    return False


def _extract_vins(payload) -> list[dict]:
    """Best-effort extraction of vehicles from the (undocumented) vehicles body.

    Returns a list of {vin, nickname?} dicts. Walks the JSON for any 17-char
    VIN-like identifier so it is robust to wrapper shape ({vehicles:[]}, list, …).
    """
    vins: dict[str, dict] = {}

    def walk(node):
        if isinstance(node, dict):
            vin = node.get("vin") or node.get("vehicleIdentificationNumber")
            if isinstance(vin, str) and len(vin) == 17:
                vins.setdefault(vin, {"vin": vin})
                nick = node.get("vehicleNickname") or node.get("nickname") or node.get("modelName")
                if nick:
                    vins[vin]["nickname"] = nick
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return list(vins.values())


class EudaApiClient:
    """Authenticated client for the EU Data Act portal."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        brand: BrandConfig,
        *,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._brand = brand
        self._country = (country or DEFAULT_COUNTRY).lower()
        self._language = (language or country or DEFAULT_LANGUAGE).lower()
        self._logged_in = False

    def _auth_headers(self, referer: str | None = None) -> dict[str, str]:
        return _login_headers(self._country, self._language, referer)

    # -- low level ---------------------------------------------------------

    async def _get(self, url: str, *, headers: dict | None = None, allow_redirects: bool = True):
        h = {"User-Agent": USER_AGENT, **(headers or {})}
        return await self._session.get(url, headers=h, allow_redirects=allow_redirects)

    async def _post_login_form(
        self,
        url: str,
        *,
        data: dict[str, str],
        referer: str,
    ):
        """POST a login form and stop after the portal callback response.

        The callback stores the authenticated session cookie and then redirects
        to a localized CMS page. Returning its response avoids downloading that
        unrelated page while preserving the cookie in the session's cookie jar.
        """
        resp = await self._session.post(
            url,
            data=data,
            headers=self._auth_headers(referer),
            allow_redirects=False,
        )
        return await self._follow_login_redirects(resp)

    async def _get_login_redirects(self, url: str, *, referer: str):
        """GET a login hop and stop after the portal callback response."""
        resp = await self._get(
            url,
            headers=self._auth_headers(referer),
            allow_redirects=False,
        )
        return await self._follow_login_redirects(resp)

    async def _follow_login_redirects(self, resp):
        """Follow login redirects and stop on the portal callback response."""
        for _ in range(_MAX_LOGIN_REDIRECTS):
            if _is_portal_callback(str(resp.url)):
                return resp
            if resp.status not in _LOGIN_REDIRECT_STATUSES:
                return resp
            location = resp.headers.get("Location")
            if not location:
                return resp
            redirect_url = urljoin(str(resp.url), location)
            redirect_referer = str(resp.url)
            resp.release()
            resp = await self._get(
                redirect_url,
                headers=self._auth_headers(redirect_referer),
                allow_redirects=False,
            )

        resp.release()
        raise ApiError(
            f"Login redirect chain exceeded {_MAX_LOGIN_REDIRECTS} hops"
        )

    # -- authentication ----------------------------------------------------

    async def async_login(self) -> None:
        """Run the full OIDC login, populating the session cookie jar."""
        try:
            await self._do_login()
        except aiohttp.ClientError as err:
            raise ApiError(f"Network error during login: {err}") from err
        self._logged_in = True

    async def _do_login(self) -> None:
        # 1. Start the OIDC flow directly at the identity provider. We build the
        #    authorize URL ourselves because the portal's
        #    /services/redirect/authentication servlet returns HTTP 500 for
        #    non-browser clients.
        authorize_url = self._authorize_url()
        _LOGGER.debug("login step1: authorize url = %s", authorize_url)
        async with await self._get(
            authorize_url,
            headers=self._auth_headers(f"{BASE_URL}/"),
        ) as resp:
            signin_url = str(resp.url)
            signin_html = await resp.text()
            signin_status = resp.status
        _LOGGER.debug("login step2: signin page = %s (%d bytes)", signin_url, len(signin_html))

        fields, action = _login_fields(signin_html)
        _LOGGER.debug("login step2: action=%s fields=%s", action, sorted(fields))

        # Auth0 Universal Login (CUPRA/SEAT): one page with username+password.
        # Classic VW identity: email identifier step, then password step.
        if _is_auth0_login(signin_url, fields):
            await self._do_auth0_login(signin_url, fields, status=signin_status)
        else:
            await self._do_classic_login(
                signin_url, fields, action, status=signin_status
            )

    async def _do_auth0_login(
        self,
        signin_url: str,
        fields: dict[str, str],
        *,
        status: int,
    ) -> None:
        """Complete Auth0 Universal Login (``/u/login``) in one POST."""
        if "state" not in fields:
            _raise_login_failure(
                f"Could not parse the Auth0 sign-in form (fields found: {sorted(fields)})",
                status=status,
            )
        fields = dict(fields)
        fields["username"] = self._email
        fields["password"] = self._password
        fields.setdefault("action", "default")
        # Keep ``?state=`` on the URL; Auth0 expects it there and in the body.
        _LOGGER.debug("login step3: Auth0 POST credentials to %s", signin_url)
        async with await self._post_login_form(
            signin_url,
            data=fields,
            referer=signin_url,
        ) as resp:
            await self._finish_login(resp)

    async def _do_classic_login(
        self,
        signin_url: str,
        fields: dict[str, str],
        action: str | None,
        *,
        status: int,
    ) -> None:
        """Complete the classic two-step VW identity login."""
        # 2. POST the email (identifier step). Fields come from HTML inputs
        #    and/or the JS templateModel (hmac, _csrf, relayState).
        if "hmac" not in fields or "_csrf" not in fields:
            _raise_login_failure(
                f"Could not parse the sign-in form (fields found: {sorted(fields)})",
                status=status,
            )
        fields = dict(fields)
        fields["email"] = self._email
        identifier_action = urljoin(signin_url, action or "")
        async with self._session.post(
            identifier_action,
            data=fields,
            headers=self._auth_headers(signin_url),
        ) as resp:
            authenticate_url = str(resp.url)
            authenticate_html = await resp.text()
            auth_status = resp.status
        _LOGGER.debug(
            "login step3: after identifier POST status=%s url=%s",
            auth_status,
            authenticate_url,
        )

        # 3. The identifier step lands on the password (authenticate) page,
        #    whose hidden fields live in the JS templateModel, not HTML inputs.
        fields2, action2 = _login_fields(authenticate_html)
        _LOGGER.debug("login step3: action=%s fields=%s", action2, sorted(fields2))
        if "hmac" not in fields2 or "_csrf" not in fields2:
            err = _login_error(authenticate_html)
            _raise_login_failure(
                err
                or "Identity portal did not return the password form - check the "
                "email address (or the login flow changed)",
                status=auth_status,
            )
        fields2["email"] = self._email
        fields2["password"] = self._password
        # The browser posts to the clean /login/authenticate URL with relayState
        # in the body; posting to authenticate_url (which carries ?relayState=)
        # duplicates it and is rejected with HTTP 400. Strip the query.
        if action2:
            authenticate_action = urljoin(authenticate_url, action2)
        else:
            authenticate_action = authenticate_url.split("?", 1)[0]
        _LOGGER.debug("login step4: POST credentials to %s", authenticate_action)

        # 4. POST credentials; follow the redirect chain back to the portal,
        #    which sets the session cookies via /services/callbacklogin.
        async with await self._post_login_form(
            authenticate_action,
            data=fields2,
            referer=authenticate_url,
        ) as resp:
            await self._finish_login(resp)

    async def _finish_login(
        self,
        resp,
        *,
        _after_terms: bool = False,
        _after_marketing: bool = False,
    ) -> None:
        """Judge the credentials redirect chain and confirm the session cookie."""
        landing = str(resp.url)

        # The callback exchanges the OIDC code, sets access_token, and responds
        # with a redirect to the localized CMS page. Do not follow that redirect.
        if _is_portal_callback(landing):
            token_cookie = resp.cookies.get("access_token")
            token = getattr(token_cookie, "value", token_cookie)
            if not token:
                raise AuthError(
                    "Login callback did not establish a session "
                    "(access_token cookie missing)"
                )
            _LOGGER.debug("login step4: access token cookie received")
            return

        # Optional marketing page. Consent is not required.
        # Classic: GET the ``callback`` query parameter (POST is rejected).
        # v2 SPA: POST relayState/state to ``…/marketing-consent/skip``.
        marketing_callback = _marketing_consent_callback(landing)
        marketing_v2 = (
            None if marketing_callback is not None else _marketing_consent_v2_skip(landing)
        )
        if marketing_callback is not None or marketing_v2 is not None:
            if _after_marketing:
                raise AuthError(
                    "Login interrupted: the identity provider still shows a "
                    "marketing consent page after it was skipped"
                )
            if marketing_callback is not None:
                _LOGGER.debug(
                    "login step4b: skip marketing consent via %s", marketing_callback
                )
                marketing_cm = await self._get_login_redirects(
                    marketing_callback,
                    referer=landing,
                )
            else:
                assert marketing_v2 is not None
                skip_url, skip_fields = marketing_v2
                _LOGGER.debug(
                    "login step4b: skip marketing consent v2 via POST %s", skip_url
                )
                marketing_cm = await self._post_login_form(
                    skip_url,
                    data=skip_fields,
                    referer=landing,
                )
            async with marketing_cm as marketing_resp:
                await self._finish_login(
                    marketing_resp,
                    _after_terms=_after_terms,
                    _after_marketing=True,
                )
            return

        landing_html = await resp.text()
        if resp.status >= 400:
            _LOGGER.debug(
                "login step4: HTTP %s body[:500]=%s",
                resp.status,
                landing_html[:500],
            )
            err = _login_error(landing_html)
            _raise_login_failure(
                err or f"Login rejected (HTTP {resp.status})",
                status=resp.status,
            )
        _LOGGER.debug("login step4: landed on %s", landing)

        # IdP terms interstitial — submit the accept form and continue the
        # redirect chain. Some accounts hit this only for non-browser clients.
        if "terms-and-conditions" in landing:
            if _after_terms:
                raise AuthError(
                    "Login interrupted: the identity provider still requires "
                    "accepting terms and conditions after submission"
                )
            fields, action = _login_fields(landing_html)
            missing = [key for key in ("_csrf", "relayState", "hmac") if key not in fields]
            if missing:
                raise AuthError(
                    "Login interrupted: the identity provider requires accepting "
                    "updated terms and conditions for this account "
                    f"(missing {', '.join(missing)} on terms form)"
                )
            if action:
                terms_action = urljoin(landing, action)
            else:
                terms_action = landing.split("?", 1)[0]
            _LOGGER.debug(
                "login step4b: POST terms accept to %s fields=%s",
                terms_action,
                sorted(fields),
            )
            async with await self._post_login_form(
                terms_action,
                data=fields,
                referer=landing,
            ) as terms_resp:
                await self._finish_login(terms_resp, _after_terms=True)
            return

        if (
            "signin-service" in landing
            or "/u/login" in landing
            or "/error" in landing
        ):
            err = _login_error(landing_html)
            raise AuthError(err or "Login failed - check email and password")
        raise AuthError(f"Login did not complete (ended at {landing})")

    @staticmethod
    def _build_authorize_url(
        brand: BrandConfig,
        *,
        country: str = DEFAULT_COUNTRY,
        language: str = DEFAULT_LANGUAGE,
    ) -> str:
        """Construct the OIDC authorize URL (bypasses the broken AEM servlet)."""
        params = {
            "client_id": brand.client_id,
            "response_type": "code",
            "scope": OIDC_SCOPE,
            "state": brand.oidc_state(country, language),
            "redirect_uri": OIDC_REDIRECT_URI,
            "prompt": "login",
        }
        return f"{OIDC_AUTHORIZE_URL}?{urlencode(params)}"

    def _authorize_url(self) -> str:
        return self._build_authorize_url(
            self._brand,
            country=self._country,
            language=self._language,
        )

    # -- authenticated requests -------------------------------------------

    async def _get_json(self, url: str, *, headers: dict | None = None, _retry: bool = True):
        try:
            async with await self._get(url, headers=headers) as resp:
                if resp.status in (401, 403) and _retry:
                    _LOGGER.debug("Session expired (%s) for %s; re-authenticating", resp.status, url)
                    self._logged_in = False
                    await self.async_login()
                    return await self._get_json(url, headers=headers, _retry=False)
                if resp.status >= 400:
                    raise ApiError(
                        f"GET {url} -> HTTP {resp.status}", status=resp.status
                    )
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise ApiError(f"Connection error for {url}: {err}") from err
        try:
            return json.loads(text)
        except ValueError as err:
            raise ApiError(f"Invalid JSON from {url}: {err}") from err

    async def async_ensure_login(self) -> None:
        if not self._logged_in:
            await self.async_login()

    async def async_list_vehicles(self) -> list[dict]:
        await self.async_ensure_login()
        payload = await self._get_json(f"{BASE_URL}{VEHICLES_PATH}?viewPosition=FRONT_LEFT")
        vehicles = _extract_vins(payload)
        # Always enrich with the friendly vehicleNickname from the relation
        # endpoint (the authoritative source, e.g. "ID.3").
        for veh in vehicles:
            try:
                rel = await self.async_get_relation(veh["vin"])
                nickname = (rel.get("relation") or {}).get("vehicleNickname")
                _LOGGER.debug("relation for %s: nickname=%r", veh["vin"], nickname)
                if nickname:
                    veh["nickname"] = nickname
            except ApiError as err:
                _LOGGER.debug("Could not fetch nickname for %s: %s", veh["vin"], err)
        return vehicles

    async def async_get_relation(self, vin: str) -> dict:
        await self.async_ensure_login()
        # The relation endpoint requires a traceid header; it returns HTTP 400
        # without one.
        headers = {"traceid": f"vehicle-relation-fetch-{uuid.uuid4()}"}
        return await self._get_json(
            f"{BASE_URL}{RELATION_PATH.format(vin=vin)}", headers=headers
        )

    async def async_get_metadata(self, vin: str) -> dict:
        """Return the data-request metadata; ``Identifier`` is needed downstream."""
        await self.async_ensure_login()
        return await self._get_json(f"{BASE_URL}{METADATA_PATH.format(vin=vin)}")

    async def async_list_datasets(self, vin: str, identifier: str) -> list[dict]:
        """Return the rolling list of available zips: [{name, createdOn, size}]."""
        await self.async_ensure_login()
        url = f"{BASE_URL}{LIST_PATH.format(vin=vin, identifier=identifier)}"
        # The list endpoint requires the data-request type header (matching
        # metadata/partial); without it the backend returns HTTP 500.
        headers = {"type": "partial"}
        try:
            async with await self._get(url, headers=headers) as resp:
                if resp.status in (401, 403):
                    self._logged_in = False
                    await self.async_login()
                    async with await self._get(url, headers=headers) as resp2:
                        resp = resp2
                if resp.status == 404:
                    # No ZIPs delivered yet for this subscription.
                    return []
                if resp.status >= 400:
                    raise ApiError(
                        f"GET {url} -> HTTP {resp.status}", status=resp.status
                    )
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise ApiError(f"Connection error for {url}: {err}") from err
        try:
            data = json.loads(text)
        except ValueError as err:
            raise ApiError(f"Invalid JSON from {url}: {err}") from err
        return data if isinstance(data, list) else data.get("files", [])

    async def async_download_dataset(self, vin: str, identifier: str, name: str) -> dict:
        """Download a specific zip by name and return the parsed JSON inside it."""
        raw = await self.async_download_dataset_raw(vin, identifier, name)
        return self.parse_dataset_zip(raw, name)

    async def async_download_dataset_raw(
        self, vin: str, identifier: str, name: str
    ) -> bytes:
        """Download a portal ZIP and return the raw bytes (for local caching)."""
        await self.async_ensure_login()
        if name.endswith(NO_CONTENT_SUFFIX):
            raise ApiError(f"{name} contains no content")
        url = f"{BASE_URL}{DOWNLOAD_PATH.format(vin=vin, identifier=identifier)}"
        headers = {"filename": name, "type": "partial"}
        try:
            async with await self._get(url, headers=headers) as resp:
                if resp.status in (401, 403):
                    self._logged_in = False
                    await self.async_login()
                    async with await self._get(url, headers=headers) as resp2:
                        if resp2.status >= 400:
                            raise ApiError(
                                f"Download {name} -> HTTP {resp2.status}",
                                status=resp2.status,
                            )
                        return await resp2.read()
                if resp.status >= 400:
                    raise ApiError(
                        f"Download {name} -> HTTP {resp.status}", status=resp.status
                    )
                return await resp.read()
        except aiohttp.ClientError as err:
            raise ApiError(f"Connection error downloading {name}: {err}") from err

    @staticmethod
    def parse_dataset_zip(raw: bytes, name: str) -> dict:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                members = [n for n in zf.namelist() if n.lower().endswith(".json")]
                if not members:
                    raise ApiError(f"No JSON inside {name}")
                with zf.open(members[0]) as fh:
                    return json.loads(fh.read().decode("utf-8"))
        except (zipfile.BadZipFile, ValueError) as err:
            raise ApiError(f"Could not read {name}: {err}") from err
