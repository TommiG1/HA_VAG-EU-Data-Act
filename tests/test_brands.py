"""Brand registry and OIDC URL tests (no Home Assistant)."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from _loader import load_modules  # noqa: E402

EXPECTED_SLUGS = (
    "volkswagen",
    "volkswagen_commercial",
    "audi",
    "skoda",
    "seat",
    "cupra",
    "bentley",
)


def main() -> int:
    mods = load_modules("const", "brands", "api")
    brands = mods["brands"]
    api = mods["api"]
    failures: list[str] = []

    def check(label, got, want):
        ok = got == want
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {got!r}" + ("" if ok else f" (want {want!r})"))
        if not ok:
            failures.append(label)

    print("brand registry:")
    check("seven brands", len(brands.BRANDS), 7)
    check("slugs", tuple(b.slug for b in brands.BRANDS), EXPECTED_SLUGS)

    client_ids = {b.client_id for b in brands.BRANDS}
    check("seat and cupra share client_id", brands.get_brand("seat").client_id, brands.get_brand("cupra").client_id)
    check(
        "vw and vw commercial share client_id",
        brands.get_brand("volkswagen").client_id,
        brands.get_brand("volkswagen_commercial").client_id,
    )
    check("distinct audi client_id", brands.get_brand("audi").client_id in client_ids, True)
    check("default brand cupra", brands.DEFAULT_BRAND, "cupra")

    print("oidc authorize urls:")
    for slug in EXPECTED_SLUGS:
        brand = brands.get_brand(slug)
        url = api.EudaApiClient._build_authorize_url(brand)
        qs = parse_qs(urlparse(url).query)
        check(f"{slug} client_id", qs.get("client_id", [""])[0], brand.client_id)
        check(f"{slug} state", qs.get("state", [""])[0], brand.oidc_state())
        check(f"{slug} redirect", qs.get("redirect_uri", [""])[0], "https://eu-data-act.drivesomethinggreater.com/login")

    cupra = brands.get_brand("cupra")
    es_url = api.EudaApiClient._build_authorize_url(cupra, country="es", language="es")
    es_qs = parse_qs(urlparse(es_url).query)
    check("cupra es state", es_qs.get("state", [""])[0], "es__es__CUPRA")

    print()
    if failures:
        print(f"FAILED: {len(failures)} -> {failures}")
        return 1
    print("ALL BRAND TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
