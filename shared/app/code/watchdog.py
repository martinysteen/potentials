#!/usr/bin/env python3
"""
watchdog.py - hourly health check of the daily chain, with email on change (SM, 2026-10-21).

Why: errors only ever ended up in ~/logs/*.log, where nobody looks. 2026-10-21 an upstream
Apps Script failure (16:11) left US rows carried for 2 h and a Drive upload stall held the
mirror for 6 min - both found by hand. This script looks at the FILES and PROCESSES the chain
leaves behind, never at a producer's internals, so it can be wrong about nothing but timing.

Checks (all skipped outside their hours; see CHECK_HOURS)
  potdat       mirror PotDat.csv creation stamp (cell A1) no older than POTDAT_MAX_AGE_MIN
  longi_stamp  longi_price.csv stamp == PotDat.csv stamp (longi saw the newest upstream file)
  mirror       mirror_status.json exit_code 0 and finished recently
  stall        a pipeline process running longer than STALL_SECONDS
  jobs         each cron job's log is fresh, and its LAST run (text after the last START line)
               holds no Traceback / ERROR line / non-zero "exit code"

  logscan      EVERY other *.log in ~/logs (any system on this machine, not only Potentials -
               the folder is shared): error lines appended since the last look, mailed once

Mail goes out only on a CHANGE (new problem, a problem that cleared) plus one OK line per day
at DIGEST_HOUR - a problem that persists is not repeated every hour. State: ~/.local/state/
potentials/watchdog.json. Credentials: ~/.config/potentials/smtp.env (NOT in the repo - the
03:40 git job pushes everything in it). Gmail needs an APP password, not the account password.

    python3 watchdog.py              # check, mail on change
    python3 watchdog.py --dry-run    # check, print, send nothing, keep state
    python3 watchdog.py --test-mail  # send one test mail and exit
"""

import argparse
import json
import re
import smtplib
import subprocess
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

HOME = Path.home()
ROOT = HOME / "potentials"
MIRROR = ROOT / "repositoryRTBI" / "data"
LOGS = HOME / "logs"
SMTP_ENV = HOME / ".config" / "potentials" / "smtp.env"
STATE = HOME / ".local" / "state" / "potentials" / "watchdog.json"

POTDAT_MAX_AGE_MIN = 100      # upstream writes hourly at ~:11
MIRROR_MAX_AGE_MIN = 100      # sync ticks :07/:14/:37/:55
STALL_SECONDS = 600           # longi's whole publish normally takes seconds
CHECK_HOURS = range(8, 23)    # upstream is quiet overnight (no PotDat 22:20 -> 07:11)
DIGEST_HOUR = 8

# name, log file, max age in minutes of its mtime, hours (local) it is expected to run
JOBS = [
    ("longi",            "start_longi.log",    75, range(0, 23)),
    ("potrank",          "run_potrank.log",    75, range(0, 23)),
    ("group_conformity", "run_conf.log",       100, range(0, 23)),
    ("strategy_grp2",    "run_production.log", 75, range(9, 23)),
    ("tunnel",           "run_tunnel.log",     26 * 60, range(0, 24)),
    ("yf3",              "start_yf3.log",      26 * 60, range(0, 24)),
]
STALL_PATTERNS = ("longi_upload.py", "rclone sync", "start_longi.sh", "run_potrank.sh",
                  "run_conf.sh", "run_production.sh")

STAMP_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4}) (\d{2})-(\d{2})")


def stamp_of(path: Path):
    """Creation stamp in cell A1 -> (datetime, raw) or (None, reason)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            first = f.readline().split(";", 1)[0].strip()
    except OSError as e:
        return None, f"{path.name} unreadable: {e}"
    m = STAMP_RE.match(first)
    if not m:
        return None, f"{path.name} A1 {first!r} is not a creation stamp"
    d, mo, y, h, mi = map(int, m.groups())
    return datetime(y, mo, d, h, mi), first[:16]


def age_min(ts: float) -> float:
    return (time.time() - ts) / 60.0


def check_potdat(now):
    if now.hour not in CHECK_HOURS:
        return {}
    dt, raw = stamp_of(MIRROR / "PotDat.csv")
    if dt is None:
        return {"potdat": raw}
    age = (now - dt).total_seconds() / 60
    if age > POTDAT_MAX_AGE_MIN:
        return {"potdat": f"PotDat.csv in the mirror is stamped {raw} ({age:.0f} min old, "
                          f"limit {POTDAT_MAX_AGE_MIN}) - upstream Apps Script or the Drive sync"}
    return {}


def check_longi_stamp(now):
    if now.hour not in CHECK_HOURS:
        return {}
    pot, praw = stamp_of(MIRROR / "PotDat.csv")
    lon, lraw = stamp_of(MIRROR / "Longi" / "longi_price.csv")
    if pot is None or lon is None:
        return {}  # reported by the potdat check / unreadable file shows in jobs
    # One hour behind is normal (upstream sometimes finishes after the :14 sync, so longi's
    # :15 run takes the previous file); two missed files is not.
    lag = (pot - lon).total_seconds() / 60
    if lag > 100:
        return {"longi_stamp": f"longi_price.csv is stamped {lraw} but PotDat.csv {praw} "
                               f"({lag:.0f} min newer): longi's publish or fetch is stuck"}
    return {}


def check_mirror(now):
    p = ROOT / "repositoryRTBI" / "mirror_status.json"
    try:
        st = json.loads(p.read_text())
        fin = datetime.fromisoformat(st["finished"]).replace(tzinfo=None)
    except Exception as e:  # noqa: BLE001 - any parse failure is the finding
        return {"mirror": f"mirror_status.json unreadable: {e}"}
    if st.get("exit_code") != 0:
        return {"mirror": f"last sync_rtbi.sh run exited {st.get('exit_code')}"}
    age = (now - fin).total_seconds() / 60
    if age > MIRROR_MAX_AGE_MIN:
        return {"mirror": f"mirror last synced {age:.0f} min ago (limit {MIRROR_MAX_AGE_MIN})"}
    return {}


def check_stall(now):
    out = subprocess.run(["ps", "-eo", "etimes,args"], capture_output=True, text=True).stdout
    found = {}
    for line in out.splitlines()[1:]:
        secs, _, args = line.strip().partition(" ")
        if not secs.isdigit() or "watchdog.py" in args or "ps -eo" in args:
            continue
        if int(secs) > STALL_SECONDS and any(p in args for p in STALL_PATTERNS):
            found[args.split()[0] + " " + " ".join(args.split()[1:3])] = int(secs)
    if found:
        what = "; ".join(f"{k.strip()[:70]} for {v // 60} min" for k, v in sorted(found.items()))
        return {"stall": f"running longer than {STALL_SECONDS // 60} min: {what}"}
    return {}


def last_run_text(text: str) -> str:
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if "START" in ln and "===" in ln or "START:" in ln]
    return "\n".join(lines[starts[-1]:]) if starts else text


def check_jobs(now):
    found = {}
    for name, fname, max_min, hours in JOBS:
        if now.hour not in hours:
            continue
        p = LOGS / fname
        if not p.exists():
            found[f"job_{name}"] = f"{fname} does not exist"
            continue
        if age_min(p.stat().st_mtime) > max_min:
            found[f"job_{name}"] = (f"{name}: {fname} not written for "
                                    f"{age_min(p.stat().st_mtime):.0f} min (limit {max_min}) - did it run?")
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 400_000))
                run = last_run_text(f.read())
        except OSError as e:
            found[f"job_{name}"] = f"{fname} unreadable: {e}"
            continue
        bad = [ln.strip() for ln in run.splitlines()
               if ln.startswith("ERROR") or "Traceback (most recent" in ln
               or re.search(r"exit code:?\s*[1-9]", ln)]
        if bad:
            found[f"job_{name}"] = f"{name}: last run has {len(bad)} error line(s), first: {bad[0][:160]}"
    return found


ERR_RE = re.compile(r"Traceback \(most recent call last\)|\bERROR\b|\bCRITICAL\b|\bFATAL\b")
# The chain jobs' own logs get the stricter last-run check above; these cron logs only repeat
# the same output, so scanning them would mail every error twice.
SCAN_SKIP = {j[1] for j in JOBS} | {"longi_cron.log", "run_potrank_cron.log", "run_conf_cron.log",
                                    "run_production_cron.log", "run_tunnel_cron.log", "watchdog.log"}
MAX_SCAN_BYTES = 2_000_000


def scan_logs(offsets: dict):
    """Every other *.log in ~/logs (any system on this box, not just Potentials): error lines
    appended since the last look. First sight of a file only records its size (no flood from
    history); a file that shrank was rotated and is read from the top.
    Returns (events, new_offsets); events = [(file, line)], de-duplicated across files."""
    events, new, seen = [], {}, set()
    for p in sorted(LOGS.glob("*.log")):
        if p.name in SCAN_SKIP:
            continue
        try:
            size = p.stat().st_size
            off = offsets.get(p.name)
            new[p.name] = size
            if off is None or size == off:
                continue
            if size < off:
                off = 0
            with open(p, "rb") as f:
                f.seek(max(off, size - MAX_SCAN_BYTES))
                chunk = f.read().decode("utf-8", errors="replace")
        except OSError:
            continue
        for ln in chunk.splitlines():
            if ERR_RE.search(ln):
                key = re.sub(r"^\S+ \S+ ", "", ln.strip())[:200]  # drop timestamp prefix
                if key not in seen:
                    seen.add(key)
                    events.append((p.name, ln.strip()[:240]))
    return events, new


def run_checks(now):
    problems = {}
    for fn in (check_potdat, check_longi_stamp, check_mirror, check_stall, check_jobs):
        try:
            problems.update(fn(now))
        except Exception as e:  # noqa: BLE001 - a broken check is itself a finding
            problems[f"watchdog_{fn.__name__}"] = f"{fn.__name__} crashed: {e!r}"
    return problems


def load_smtp():
    cfg = {}
    for ln in SMTP_ENV.read_text().splitlines():
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1)
            cfg[k.strip()] = v.strip().strip("'\"")
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "ALERT_TO"):
        if not cfg.get(k):
            raise SystemExit(f"{SMTP_ENV}: {k} missing")
    return cfg


def send(subject: str, body: str):
    cfg = load_smtp()
    msg = EmailMessage()
    msg["From"] = cfg["SMTP_USER"]
    msg["To"] = cfg["ALERT_TO"]
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"]), timeout=30) as s:
        s.starttls()
        s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"].replace(" ", ""))
        s.send_message(msg)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-mail", action="store_true")
    a = ap.parse_args()

    if a.test_mail:
        send("[potentials] test mail", "The watchdog can reach you. Nothing else to do.")
        print("test mail sent")
        return 0

    now = datetime.now()
    problems = run_checks(now)
    try:
        prev = json.loads(STATE.read_text())
    except (OSError, ValueError):
        prev = {"problems": {}, "digest_day": ""}
    old = prev.get("problems", {})

    new = {k: v for k, v in problems.items() if k not in old}
    cleared = {k: old[k] for k in old if k not in problems}
    digest = now.hour == DIGEST_HOUR and prev.get("digest_day") != now.strftime("%F")

    events, offsets = scan_logs(prev.get("offsets", {}))

    print(f"{now:%F %T} problems={len(problems)} new={len(new)} cleared={len(cleared)} "
          f"log_errors={len(events)}")
    for k, v in sorted(problems.items()):
        print(f"  PROBLEM {k}: {v}")
    for fn, ln in events[:20]:
        print(f"  LOG {fn}: {ln}")

    mails = []
    if events:
        files = sorted({fn for fn, _ in events})
        shown = "\n".join(f"- {fn}: {ln}" for fn, ln in events[:15])
        more = f"\n... and {len(events) - 15} more" if len(events) > 15 else ""
        mails.append((f"[potentials] LOG ERRORS: {len(events)} new in {len(files)} file(s)",
                      f"New error lines in ~/logs since the last check:\n{shown}{more}"))
    if new:
        mails.append((f"[potentials] PROBLEM: {len(new)} new", "\n".join(f"- {v}" for v in new.values())
                      + ("\n\nStill open:\n" + "\n".join(f"- {v}" for k, v in problems.items() if k not in new)
                         if len(problems) > len(new) else "")))
    if cleared:
        mails.append((f"[potentials] RECOVERED: {len(cleared)}",
                      "\n".join(f"- {v}" for v in cleared.values())
                      + ("" if problems else "\n\nNothing is open now.")))
    if digest and not problems and not new and not cleared:
        mails.append(("[potentials] daily: all checks OK", f"All checks passed at {now:%F %H:%M}."))

    if a.dry_run:
        for s, b in mails:
            print(f"--- would mail: {s}\n{b}")
        return 0

    for s, b in mails:
        try:
            send(s, b)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: mail failed ({e!r}) - state NOT advanced so the next run retries")
            return 1
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"problems": problems, "offsets": offsets,
                                 "digest_day": now.strftime("%F") if digest else prev.get("digest_day", "")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
