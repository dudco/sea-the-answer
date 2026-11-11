"""Publish simulated UTC days, from the departure date up to now, to the app.

Both the one-way voyage and the round-trip scenario publish only UTC days that
have finished by --through (default: now); future days are never published.
The default is a preview. Use --apply to append the missing records. For a
scheduled invocation, provide HAEDAP_SIM_PASSWORD via its secret store.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from getpass import getpass
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

from scripts.simulate_round_trip import DEFAULT_DEPARTURE, build_round_trip
from scripts.simulate_voyage import advance, print_warnings


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AdminClient:
    def __init__(self, origin: str):
        parts = urlsplit(origin)
        if (parts.scheme != "https" or not parts.hostname or parts.username is not None
                or parts.path not in ("", "/") or parts.query or parts.fragment):
            raise ValueError("--server must be an HTTPS origin without credentials or a path")
        self.origin = origin.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())
        self.token = self.identity = ""

    def request(self, path: str, body: dict | None = None) -> dict:
        headers = {"Accept": "application/json", "X-Haedap-Identity": self.identity}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers.update({"Content-Type": "application/json", "X-Haedap-Token": self.token, "Origin": self.origin})
        try:
            with self.opener.open(Request(self.origin + "/api/" + path, data, headers), timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            # Server bodies can include workspace data. Report the status and endpoint only.
            raise ValueError(f"Server rejected {path} (HTTP {exc.code})") from None
        except URLError:
            raise ValueError(f"Could not reach {path} over HTTPS") from None

    def login(self, username: str, password: str) -> None:
        self.token = self.request("health")["csrfToken"]
        self.request("auth/login", {"username": username, "password": password})
        health = self.request("health")
        self.token = health["csrfToken"]
        user = health.get("user") or {}
        self.identity = user.get("id", "")
        if not health.get("authenticated") or user.get("role") != "admin" or user.get("must_change_password"):
            raise ValueError("Publishing requires an active administrator account")


def pending_records(remote: dict, ship: dict, records: list[dict]) -> tuple[bool, list[dict]]:
    existing_ship = next((row for row in remote["ships"] if row["id"] == ship["id"]), None)
    if existing_ship is not None and any(existing_ship.get(key) != value for key, value in ship.items()):
        raise ValueError("The existing ship differs from the simulation; no data was written")

    by_id = {row["id"]: row for row in remote["records"]}
    by_date = {row["date"]: row for row in remote["records"] if row["ship"] == ship["id"]}
    pending = []
    for row in records:
        existing = by_date.get(row["date"], by_id.get(row["id"]))
        if existing is None:
            pending.append(row)
        elif any(existing.get(key) != value for key, value in row.items()):
            raise ValueError(f"Existing record differs on {row['date']}; no data was written")
    return existing_ship is None, pending


def publish(client: AdminClient, result: dict, *, apply: bool) -> dict:
    ship = result["ships"][0]
    records = result["records"]
    ship_missing, pending = pending_records(client.request("operations"), ship, records)
    if apply and pending:
        if ship_missing:
            client.request("changes", {"kind": "ship.save", "payload": ship})
        check = client.request("operations/validate", {"rows": pending})
        if not check.get("valid"):
            raise ValueError("The app rejected the simulated daily records during validation")
        client.request("changes", {"kind": "operation.import", "payload": {"rows": pending}})
        if pending_records(client.request("operations"), ship, records)[1]:
            raise ValueError("The app did not return all expected records after import")
    return {"ship": ship["id"], "completed_days": len(records),
            "already_present": len(records) - len(pending),
            "pending_days": 0 if apply else len(pending), "imported_days": len(pending) if apply else 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, help="HTTPS origin of the app")
    parser.add_argument("--username", required=True, help="app administrator username")
    parser.add_argument("--database", type=Path, help="one-way simulation's SQLite log")
    parser.add_argument("--departure", type=date.fromisoformat,
                        help=f"departure date: one-way at UTC midnight, round trip at 12:00 UTC (default {DEFAULT_DEPARTURE})")
    parser.add_argument("--through", type=datetime.fromisoformat, help="snapshot timestamp with offset (default: now)")
    parser.add_argument("--round-trip", action="store_true", help="use the 60-day Incheon–Port Said–Incheon scenario")
    parser.add_argument("--apply", action="store_true", help="append missing days to the app")
    parser.add_argument("--password-stdin", action="store_true", help="read one password line from stdin")
    args = parser.parse_args()
    if args.round_trip and args.database is not None:
        parser.error("--round-trip does not use a SQLite log; omit --database")
    if not args.round_trip and (args.database is None or args.departure is None):
        parser.error("--database and --departure are required for a one-way voyage")
    try:
        now = datetime.now(UTC)
        through = args.through or now
        if through.utcoffset() is None:
            raise ValueError("--through must include a UTC offset, such as Z or +09:00")
        if args.apply and through > now:
            raise ValueError("Publishing requires a snapshot time at or before the present")
        if args.round_trip:
            result = build_round_trip(args.departure or DEFAULT_DEPARTURE, through)
        else:
            result = advance(args.database, args.departure, through)
        print_warnings(result)
        client = AdminClient(args.server)
        password = (sys.stdin.readline().rstrip("\r\n") if args.password_stdin else
                    os.environ.get("HAEDAP_SIM_PASSWORD") or getpass("App password: "))
        if not password:
            raise ValueError("An administrator password is required")
        try:
            client.login(args.username, password)
            del password
            summary = publish(client, result, apply=args.apply)
            summary["warnings"] = result["simulation"]["warnings"]
            print(json.dumps(summary, ensure_ascii=False))
        finally:
            if client.identity:
                client.request("auth/logout", {})
    except (KeyError, ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"publish_simulated_voyage: {exc}\n")


if __name__ == "__main__":
    main()
