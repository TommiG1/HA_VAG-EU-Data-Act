"""Additional API branch coverage with an in-memory HTTP session."""
from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import AsyncMock

import aiohttp
import pytest

from custom_components.cupra_eu_data_act.api import ApiError, AuthError, EudaApiClient
from custom_components.cupra_eu_data_act.brands import get_brand
from custom_components.cupra_eu_data_act.const import NO_CONTENT_SUFFIX


class Response:
    def __init__(self, status=200, body="", url="https://example.test/", headers=None):
        self.status = status
        self.body = body
        self.url = url
        self.headers = headers or {}
        self.history = []
        self.cookies = {}

    async def text(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body

    async def read(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body if isinstance(self.body, bytes) else self.body.encode()

    def release(self):
        pass

    def __await__(self):
        async def result():
            return self

        return result().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, *args, **kwargs):
        self.requests.append(("get", args, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def post(self, *args, **kwargs):
        self.requests.append(("post", args, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def client(session, logged_in=True):
    value = EudaApiClient(session, "a@b.c", "secret", get_brand("cupra"))
    value._logged_in = logged_in
    return value


async def test_json_vehicle_relation_and_metadata_paths() -> None:
    session = Session(
        Response(body='{"vehicles":[{"vin":"WVWZZZTESTVIN0001"}]}'),
        Response(body='{"relation":{"vehicleNickname":"Born"}}'),
        Response(body='{"Identifier":"id"}'),
    )
    api = client(session)
    vehicles = await api.async_list_vehicles()
    assert vehicles[0]["nickname"] == "Born"
    assert (await api.async_get_metadata("WVWZZZTESTVIN0001"))["Identifier"] == "id"

    session = Session(
        Response(body='{"vehicles":[{"vin":"WVWZZZTESTVIN0001"}]}'),
        Response(status=500),
    )
    assert (await client(session).async_list_vehicles())[0]["vin"]


async def test_get_json_reauth_errors_network_and_invalid_json(monkeypatch) -> None:
    session = Session(Response(status=401), Response(body='{"ok":true}'))
    api = client(session)
    monkeypatch.setattr(api, "async_login", pytest.importorskip("unittest.mock").AsyncMock())
    assert await api._get_json("https://x") == {"ok": True}

    with pytest.raises(ApiError):
        await client(Session(Response(status=500)))._get_json("https://x")
    with pytest.raises(ApiError):
        await client(Session(Response(body="bad")))._get_json("https://x")
    with pytest.raises(ApiError):
        await client(Session(aiohttp.ClientConnectionError("down")))._get_json(
            "https://x"
        )


async def test_list_dataset_error_shapes_and_connection(monkeypatch) -> None:
    assert await client(Session(Response(status=404))).async_list_datasets("V", "I") == []
    with pytest.raises(ApiError):
        await client(Session(Response(status=500))).async_list_datasets("V", "I")
    with pytest.raises(ApiError):
        await client(Session(Response(body="bad"))).async_list_datasets("V", "I")
    assert await client(Session(Response(body='{"files":[{"name":"x"}]}'))).async_list_datasets(
        "V", "I"
    ) == [{"name": "x"}]
    with pytest.raises(ApiError):
        await client(Session(aiohttp.ClientError("down"))).async_list_datasets("V", "I")

    api = client(Session(Response(status=401), Response(body="[]")))
    monkeypatch.setattr(api, "async_login", pytest.importorskip("unittest.mock").AsyncMock())
    assert await api.async_list_datasets("V", "I") == []


async def test_download_paths_and_zip_parsing(monkeypatch) -> None:
    with pytest.raises(ApiError):
        await client(Session()).async_download_dataset_raw(
            "V", "I", f"x{NO_CONTENT_SUFFIX}"
        )
    with pytest.raises(ApiError):
        await client(Session(Response(status=500))).async_download_dataset_raw(
            "V", "I", "x.zip"
        )
    with pytest.raises(ApiError):
        await client(Session(aiohttp.ClientError("down"))).async_download_dataset_raw(
            "V", "I", "x.zip"
        )

    api = client(Session(Response(status=401), Response(status=500)))
    monkeypatch.setattr(api, "async_login", pytest.importorskip("unittest.mock").AsyncMock())
    with pytest.raises(ApiError):
        await api.async_download_dataset_raw("V", "I", "x.zip")

    api = client(Session(Response(status=401), Response(body=b"zip")))
    monkeypatch.setattr(api, "async_login", pytest.importorskip("unittest.mock").AsyncMock())
    assert await api.async_download_dataset_raw("V", "I", "x.zip") == b"zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps({"ok": True}))
    api = client(Session(Response(body=buf.getvalue())))
    assert await api.async_download_dataset("V", "I", "x.zip") == {"ok": True}
    with pytest.raises(ApiError):
        EudaApiClient.parse_dataset_zip(b"not zip", "bad.zip")
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w"):
        pass
    with pytest.raises(ApiError):
        EudaApiClient.parse_dataset_zip(empty.getvalue(), "empty.zip")


async def test_redirect_and_login_network_branches() -> None:
    api = client(Session(Response(status=200, url="https://example.test/end")))
    response = await api._get_login_redirects("https://example.test/start", referer="https://r")
    assert response.status == 200
    api = client(Session(Response(status=302, url="https://x", headers={})))
    assert (await api._follow_login_redirects(api._session.responses.pop())).status == 302

    api = client(Session(aiohttp.ClientError("down")), logged_in=False)
    with pytest.raises(ApiError):
        await api.async_login()
    api = client(Session(), logged_in=True)
    await api.async_ensure_login()
    api = client(Session(), logged_in=False)
    api.async_login = AsyncMock()
    await api.async_ensure_login()
    api.async_login.assert_awaited_once()


async def test_classic_and_auth0_malformed_forms() -> None:
    api = client(Session())
    with pytest.raises(AuthError):
        await api._do_auth0_login("https://x/u/login", {}, status=401)
    with pytest.raises(AuthError):
        await api._do_classic_login("https://x", {}, None, status=401)


async def test_classic_login_happy_path() -> None:
    password_form = """
    <form action="/login/authenticate">
      <input name="hmac" value="h2">
      <input name="_csrf" value="c2">
      <input name="relayState" value="r2">
    </form>
    """
    identifier_response = Response(
        body=password_form,
        url="https://identity.vwgroup.io/login/authenticate?relayState=r2",
    )
    callback = Response(
        status=302,
        url="https://eu-data-act.drivesomethinggreater.com/services/callbacklogin",
    )
    callback.cookies["access_token"] = "token"
    api = client(Session(identifier_response, callback))
    await api._do_classic_login(
        "https://identity.vwgroup.io/login/identifier",
        {"hmac": "h1", "_csrf": "c1", "relayState": "r1"},
        "/login/identifier",
        status=200,
    )
