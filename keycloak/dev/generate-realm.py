#!/usr/bin/env python3
"""Derive keycloak/dev/realm-with-theme.json from keycloak/cdip-dev-realm.json.

The fixture is the dev realm export plus what the theme harness needs: the gundi login theme,
plain http (containerised Chrome reaches Keycloak over http via host.docker.internal), a
displayNameHtml carrying Keycloak's default logo markup (a prod realm may carry it; the theme must
hide it), and a user forced through the update-password and configure-OTP pages.

    keycloak/dev/generate-realm.py           # rewrite the fixture
    keycloak/dev/generate-realm.py --check   # exit 1 if the fixture is stale (CI)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "keycloak" / "cdip-dev-realm.json"
TARGET = ROOT / "keycloak" / "dev" / "realm-with-theme.json"

THEME_TESTER = {
    "username": "theme-tester",
    "enabled": True,
    "email": "theme-tester@example.com",
    "firstName": "Theme",
    "lastName": "Tester",
    "credentials": [{"type": "password", "value": "theme-tester", "temporary": False}],
    "requiredActions": ["UPDATE_PASSWORD", "CONFIGURE_TOTP"],
}


def build() -> str:
    realm = json.loads(SOURCE.read_text())
    realm["loginTheme"] = "gundi"
    realm["sslRequired"] = "none"
    realm["displayNameHtml"] = '<div class="kc-logo-text"><span>Keycloak</span></div>'
    users = [u for u in realm.get("users", []) if u.get("username") != THEME_TESTER["username"]]
    realm["users"] = users + [THEME_TESTER]
    return json.dumps(realm, indent=2) + "\n"


def main(argv: list[str]) -> int:
    content = build()
    if "--check" in argv:
        current = TARGET.read_text() if TARGET.exists() else ""
        if current != content:
            print(f"{TARGET.relative_to(ROOT)} is stale; run {Path(__file__).relative_to(ROOT)}", file=sys.stderr)
            return 1
        print(f"OK: {TARGET.relative_to(ROOT)} matches {SOURCE.relative_to(ROOT)}")
        return 0
    TARGET.write_text(content)
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
