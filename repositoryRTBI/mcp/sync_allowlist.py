#!/usr/bin/env python
"""Sync a Google Group's members into the allowlist file mcp/allowed_group.txt.

The plot service (api/plot.py) and the MCP server (server.py) allow an email if it is in
RTBI_MCP_ALLOWED_EMAILS (mcp/.env, manual entries) OR in allowed_group.txt (this script).
Group membership is read through the Admin SDK Directory API with a service account that has
domain-wide delegation for ONE read-only scope (admin.directory.group.member.readonly),
impersonating a Workspace admin. Key: ~/.config/potentials/allowlist_sa.json (outside the repo).

Safety:
  - default is a DRY RUN: prints the members, writes nothing. --write is needed to change the file.
  - any API error -> the file is left exactly as it was (a Google outage never locks users out).
  - an EMPTY result is refused (a mistyped group / lost rights must not wipe access); nothing written.
  - nested groups are expanded (includeDerivedMembership); only active USER members count.
  - the file is replaced atomically, never half-written.

Run on the server inside potsystem_env:
    python sync_allowlist.py            # dry run
    python sync_allowlist.py --write
"""
import argparse
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPE = "https://www.googleapis.com/auth/admin.directory.group.member.readonly"
KEY = Path.home() / ".config" / "potentials" / "allowlist_sa.json"
OUT = Path(__file__).resolve().parent / "allowed_group.txt"
DEFAULT_GROUP = "rtbi-selectstock@innovia.dk"
DEFAULT_ADMIN = "sm@innovia.dk"


def group_members(group: str, admin: str) -> set[str]:
    creds = service_account.Credentials.from_service_account_file(
        str(KEY), scopes=[SCOPE], subject=admin)
    svc = build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    emails, token = set(), None
    while True:
        resp = svc.members().list(groupKey=group, includeDerivedMembership=True,
                                  maxResults=200, pageToken=token).execute()
        for m in resp.get("members", []):
            if m.get("type") == "USER" and m.get("status", "ACTIVE") == "ACTIVE" and m.get("email"):
                emails.add(m["email"].strip().lower())
        token = resp.get("nextPageToken")
        if not token:
            return emails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--group", default=DEFAULT_GROUP)
    ap.add_argument("--admin", default=DEFAULT_ADMIN, help="Workspace admin the service account impersonates")
    ap.add_argument("--write", action="store_true", help="update allowed_group.txt (default: dry run)")
    a = ap.parse_args()

    try:
        emails = group_members(a.group, a.admin)
    except Exception as e:                       # noqa: BLE001 - any failure must leave the file alone
        print(f"{datetime.now():%F %T} ERROR reading {a.group}: {e}", file=sys.stderr)
        return 1
    if not emails:
        print(f"{datetime.now():%F %T} ERROR {a.group} returned no members; file NOT changed", file=sys.stderr)
        return 1

    old = set(OUT.read_text().split()) if OUT.exists() else set()
    print(f"{a.group}: {len(emails)} members (file now has {len(old)}); "
          f"+{len(emails - old)} -{len(old - emails)}")
    for e in sorted(emails):
        print(("  + " if e not in old else "    ") + e)
    for e in sorted(old - emails):
        print("  - " + e)
    if not a.write:
        print("dry run: nothing written (use --write)")
        return 0
    fd, tmp = tempfile.mkstemp(dir=OUT.parent, prefix=".allowed_group.")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(sorted(emails)) + "\n")
    os.replace(tmp, OUT)
    print(f"written {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
