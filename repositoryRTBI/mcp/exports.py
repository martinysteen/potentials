"""
exports.py - complete-result CSV downloads and per-member API keys for the MCP server.

The tools answer small questions inline. When the answer is big (or the caller asks for a file),
the COMPLETE result is written here as a CSV and the tool replies with a download link:

    https://mcp.innovia.dk/dl/<random token>/<name>.csv

Each link belongs to the member whose tool call made it (their email sits in the export's
folder as `.owner`, never in the URL). The download route in server.py serves it either way:
  - the link alone (a click in a browser): allowed while the link's OWNER is on the allowlist;
  - with a personal API key (`Authorization: Bearer <key>` or `X-API-Key: <key>`): allowed while
    the KEY's owner is on the allowlist - for scripts and agents; a wrong key is refused.
The allowlist is read as it stands now, on EVERY fetch, so a member removed from it loses every
link they ever made, at once. A link with no owner (made without a signed-in caller) needs a key.
A leaked link works for whoever holds it until it expires (TTL_HOURS) or its owner is removed.

Where things live (both outside the repo: ~/git_pot.sh at 03:40 pushes uncommitted repo files):
    keys      ~/.config/potentials/mcp_keys.json   {email: {"hash": sha256, "created": iso}}
              only the hash is stored - a key is shown to its member once, never recoverable
    exports   ~/.cache/potentials/mcp-exports/<token>/<name>.csv   NOT served by Caddy
              (the old /srv/tunnel-reports folder is public static; these are not)

Override with RTBI_MCP_KEYS / RTBI_MCP_EXPORT_DIR / RTBI_MCP_BASE_URL (smoke_test.py does).
Exports are deleted after TTL_HOURS. CSV is standard (comma, decimal point), unlike the
repository's European files - these go to scripts and chat tools, not back into the chain.

Admin from the command line (via ssh + potsystem_env):
    python exports.py list              who holds a key, and since when
    python exports.py revoke <email>    kill that member's key (their links stop working)
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

TTL_HOURS = 24
MAX_CELLS = 20_000_000          # rows x columns of one export (the full tunnel history is ~6M)
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,120}$")
OWNER_FILE = ".owner"

# Who is calling right now (the signed-in member's email, lower case) - server.py sets this to
# read the OAuth token. Every export is stamped with it; None = no identity, the link needs a key.
caller_email: Callable[[], str | None] = lambda: None


class ExportError(Exception):
    """An export that cannot be made - message is meant for the LLM caller."""


def export_dir() -> Path:
    return Path(os.environ.get("RTBI_MCP_EXPORT_DIR", Path.home() / ".cache" / "potentials" / "mcp-exports"))


def keys_file() -> Path:
    return Path(os.environ.get("RTBI_MCP_KEYS", Path.home() / ".config" / "potentials" / "mcp_keys.json"))


def base_url() -> str:
    return os.environ.get("RTBI_MCP_BASE_URL", "https://mcp.innovia.dk").rstrip("/")


# --------------------------------------------------------------------------- #
# exports                                                                     #
# --------------------------------------------------------------------------- #

def _cleanup(root: Path) -> None:
    cutoff = time.time() - TTL_HOURS * 3600
    for d in root.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def write_csv(frame: pd.DataFrame, basename: str, index: bool = False, index_label=None,
             what: str = "The COMPLETE result") -> dict:
    """Write the COMPLETE `frame` as <basename>.csv in a folder of its own; return the reply fields."""
    if frame.size > MAX_CELLS:
        raise ExportError(f"{frame.size} values is too large for one download (limit {MAX_CELLS}). "
                          "Narrow the tickers, dates or filter.")
    root = export_dir()
    root.mkdir(parents=True, exist_ok=True)
    _cleanup(root)
    token = secrets.token_urlsafe(12)
    folder = root / token
    folder.mkdir()
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", basename) + ".csv"
    frame.to_csv(folder / name, index=index, index_label=index_label)
    owner = (caller_email() or "").strip().lower()
    if owner:
        (folder / OWNER_FILE).write_text(owner, encoding="utf-8")
    return {"download_url": f"{base_url()}/dl/{token}/{name}",
            "download_note": f"{what} ({len(frame)} rows x {len(frame.columns) + bool(index)} columns) "
                             "as a standard CSV (comma, decimal point). Give the link to the user to open in a "
                             "browser - no key needed, it is tied to their account. Scripts and agents fetching "
                             "it can also send the member's API key as 'Authorization: Bearer <key>' "
                             f"(create_api_key tool). The link expires after {TTL_HOURS} hours."}


def resolve(token: str, name: str) -> Path | None:
    """The file behind /dl/<token>/<name>, or None (unknown, malformed, expired)."""
    if not (_TOKEN.match(token) and _NAME.match(name)) or ".." in name:
        return None
    p = export_dir() / token / name
    try:
        if not p.is_file() or p.stat().st_mtime < time.time() - TTL_HOURS * 3600:
            return None
    except OSError:
        return None
    return p


def link_owner(path: Path) -> str | None:
    """The email of the member who made the export at `path` (a resolve() result), or None."""
    try:
        return (path.parent / OWNER_FILE).read_text(encoding="utf-8").strip().lower() or None
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# API keys                                                                    #
# --------------------------------------------------------------------------- #

def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _read() -> dict:
    p = keys_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ExportError("The key store is unreadable - tell sm@innovia.dk.")


def _update(mutate) -> None:
    """Read-modify-write under a file lock, atomically replaced, mode 0600."""
    p = keys_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read()
        mutate(data)
        tmp = p.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, p)


def create_key(email: str) -> str:
    """A fresh key for `email`; any earlier key of theirs stops working. Returned once."""
    key = "pk_" + secrets.token_urlsafe(32)
    entry = {"hash": _hash(key), "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")}
    _update(lambda d: d.__setitem__(email.lower(), entry))
    return key


def owner_of(key: str) -> str | None:
    """The email a key belongs to, or None."""
    if not key:
        return None
    h = _hash(key)
    found = None
    for email, entry in _read().items():          # no early exit: constant work per lookup
        if hmac.compare_digest(entry.get("hash", ""), h):
            found = email
    return found


def revoke(email: str) -> bool:
    gone = []
    _update(lambda d: gone.append(d.pop(email.lower(), None)))
    return gone[0] is not None


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "list":
        for e, v in sorted(_read().items()):
            print(f"{e:40s} key created {v.get('created', '?')}")
    elif cmd == "revoke" and len(sys.argv) == 3:
        print("revoked" if revoke(sys.argv[2]) else "no key for that email")
    else:
        raise SystemExit(__doc__.split("Admin from the command line")[1])
