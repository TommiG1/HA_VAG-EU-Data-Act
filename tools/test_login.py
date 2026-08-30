#!/usr/bin/env python3
"""Standalone tester for the EU Data Act login flow (no Home Assistant needed).

Runs the *real* EudaApiClient login against the live portal so you can debug
authentication outside Home Assistant.

Setup (once):
    python3 -m venv .venv
    .venv/bin/pip install aiohttp

Run:
    EUDA_EMAIL='you@example.com' EUDA_PASSWORD='secret' EUDA_BRAND='audi' \\
        .venv/bin/python tools/test_login.py

    .venv/bin/python tools/test_login.py --brand cupra you@example.com 'secret'
    .venv/bin/python tools/test_login.py --brand cupra --country es you@example.com 'secret'
    .venv/bin/python tools/test_login.py --list-brands

Exit codes:
    0 = login OK and real dataset downloaded
    1 = login or API error
    2 = login OK but no real data yet (empty list or _no_content_found only)
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "custom_components" / "cupra_eu_data_act"
PKG = "cupra_eu_data_act"


def _load():
    """Load integration modules without importing Home Assistant."""
    try:
        import aiohttp  # noqa: F401
    except ModuleNotFoundError:
        print("ERROR: aiohttp is not installed. Run: .venv/bin/pip install aiohttp")
        sys.exit(2)
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules[PKG] = pkg
    mods = {}
    for name in ("const", "brands", "data", "api"):
        spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", PKG_DIR / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = PKG
        sys.modules[f"{PKG}.{name}"] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods


async def run_normal(
    mods,
    brand_slug: str,
    email: str,
    password: str,
    *,
    country: str,
    language: str,
) -> int:
    import aiohttp

    api = mods["api"]
    const = mods["const"]
    brand = mods["brands"].get_brand(brand_slug)

    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
    client = api.EudaApiClient(
        session,
        email,
        password,
        brand,
        country=country,
        language=language,
    )
    try:
        print(f"\n=== Brand: {brand.title} ({brand_slug}) ===")
        print(f"=== OIDC state: {brand.oidc_state(country, language)} ===")
        print("\n=== Logging in ===")
        await client.async_login()
        print("LOGIN OK\n")

        print("=== Vehicles ===")
        vehicles = await client.async_list_vehicles()
        for v in vehicles:
            print(f"  {v.get('vin')}  nickname={v.get('nickname')}")
        if not vehicles:
            print("  (no vehicles returned - check portal vehicle link + brand)")
            return 1

        vin = vehicles[0]["vin"]
        print(f"\n=== Metadata for {vin} ===")
        meta = await client.async_get_metadata(vin)
        identifier = meta.get("Identifier")
        print(f"  Identifier={identifier}  Frequency={meta.get('Frequency')}")

        if not identifier:
            print("\nNO SUBSCRIPTION: enable a continuous 15-minute data request on the portal first.")
            return 2

        print(f"\n=== Dataset list for {vin} ===")
        datasets = await client.async_list_datasets(vin, identifier)
        print(f"  {len(datasets)} file(s) in delivery list")
        for d in datasets[:5]:
            print(f"    {d.get('name')}  createdOn={d.get('createdOn')}")

        content = [
            d
            for d in datasets
            if d.get("name") and not d["name"].endswith(const.NO_CONTENT_SUFFIX)
        ]
        empty = [d for d in datasets if d.get("name", "").endswith(const.NO_CONTENT_SUFFIX)]

        if not datasets:
            print(
                "\nWAITING: subscription active but no ZIPs yet (normal right after creating the request)."
            )
            return 2

        if not content:
            print(
                f"\nNO CONTENT YET: {len(empty)} empty snapshot(s) (_no_content_found). "
                "Login and portal setup work; wait for the next 15-minute interval."
            )
            return 2

        newest = content[-1]["name"]
        print(f"\n=== Downloading {newest} ===")
        payload = await client.async_download_dataset(vin, identifier, newest)
        print(f"  parsed JSON: vin={payload.get('vin')} points={len(payload.get('Data', []))}")
        print("\nALL OK — integration path verified end-to-end")
        return 0
    except Exception as err:  # noqa: BLE001
        print(f"\nFAILED: {type(err).__name__}: {err}")
        return 1
    finally:
        await session.close()


async def run_dump(
    mods,
    brand_slug: str,
    email: str,
    *,
    country: str,
    language: str,
) -> int:
    """Walk the flow manually, saving each page and listing all forms."""
    import aiohttp
    from html.parser import HTMLParser
    from urllib.parse import urljoin

    api = mods["api"]
    const = mods["const"]
    brand = mods["brands"].get_brand(brand_slug)

    class AllForms(HTMLParser):
        def __init__(self):
            super().__init__()
            self.forms = []
            self._cur = None

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "form":
                self._cur = {"action": a.get("action"), "fields": {}}
                self.forms.append(self._cur)
            elif tag == "input" and self._cur is not None:
                if a.get("name"):
                    self._cur["fields"][a["name"]] = a.get("value") or ""

        def handle_endtag(self, tag):
            if tag == "form":
                self._cur = None

    def dump(name, url, html):
        path = Path("/tmp") / f"euda_{name}.html"
        path.write_text(html, encoding="utf-8")
        p = AllForms()
        p.feed(html)
        print(f"\n--- {name}: {url}")
        print(f"    saved {len(html)} bytes -> {path}")
        for i, f in enumerate(p.forms):
            print(f"    form[{i}] action={f['action']} fields={sorted(f['fields'])}")
        if not p.forms:
            print("    (no <form> tags found - page may be JS-rendered)")

    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
    client = api.EudaApiClient(
        session, email, "unused", brand, country=country, language=language
    )
    try:
        async with await client._get(f"{const.BASE_URL}/") as resp:
            await resp.read()

        authorize_url = api.EudaApiClient._build_authorize_url(
            brand, country=country, language=language
        )
        print(f"\nBrand: {brand.title}")
        print(f"authorize_url = {authorize_url}")
        async with await client._get(authorize_url) as resp:
            signin_url, signin_html = str(resp.url), await resp.text()
        dump("2_signin", signin_url, signin_html)

        fields, action = api._login_fields(signin_html)
        print(f"\nstep2 extracted: action={action} fields={sorted(fields)}")
        fields["email"] = email
        async with session.post(
            urljoin(signin_url, action or ""), data=fields, headers={"User-Agent": api.USER_AGENT}
        ) as resp:
            auth_url, auth_html = str(resp.url), await resp.text()
        dump("3_authenticate", auth_url, auth_html)

        fields2, _ = api._login_fields(auth_html)
        print(f"\nstep3 fields={sorted(fields2)}")
        print("step3 has hmac+_csrf:", "hmac" in fields2 and "_csrf" in fields2)
        print("\nNo password was sent in --dump mode.")
        return 0
    finally:
        await session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test EU Data Act portal login")
    parser.add_argument(
        "--brand",
        default=os.environ.get("EUDA_BRAND", "cupra"),
        help="Brand slug: volkswagen, audi, skoda, seat, cupra, bentley, volkswagen_commercial",
    )
    parser.add_argument(
        "--country",
        default=os.environ.get("EUDA_COUNTRY", "de"),
        help="Two letter country code for OIDC state (default: de)",
    )
    parser.add_argument(
        "--language",
        default=os.environ.get("EUDA_LANGUAGE"),
        help="Two letter language code (defaults to --country)",
    )
    parser.add_argument("--dump", action="store_true", help="Dump login HTML without sending password")
    parser.add_argument("--list-brands", action="store_true", help="List supported brand slugs")
    parser.add_argument("email", nargs="?", default=os.environ.get("EUDA_EMAIL"))
    parser.add_argument("password", nargs="?", default=os.environ.get("EUDA_PASSWORD"))
    args = parser.parse_args()

    mods = _load()
    brands = mods["brands"]

    if args.list_brands:
        for slug, title in brands.brand_options():
            b = brands.get_brand(slug)
            print(f"{slug:22} {title:32} state={b.oidc_state_key}")
        return 0

    if not args.email:
        args.email = input("Email: ")
    if not args.dump and not args.password:
        import getpass

        args.password = getpass.getpass("Password: ")

    try:
        brands.get_brand(args.brand)
    except ValueError:
        print(f"Unknown brand {args.brand!r}. Use --list-brands.")
        return 1

    country = (args.country or "de").lower()
    language = (args.language or country).lower()

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    if args.dump:
        return asyncio.run(
            run_dump(mods, args.brand, args.email, country=country, language=language)
        )
    return asyncio.run(
        run_normal(
            mods,
            args.brand,
            args.email,
            args.password,
            country=country,
            language=language,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
