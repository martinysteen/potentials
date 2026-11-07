"""
smoke_test.py - exercise every tool through FastMCP's in-memory client (no HTTP,
no auth), and check the monthly gain against a hand computation from PotDat.csv.

    cd ~/potentials/repositoryRTBI/mcp && python smoke_test.py
"""
import asyncio
import os
from pathlib import Path

# In-memory: test the tools, not the auth. Set empty rather than pop: server.py's
# load_dotenv() never overrides an existing variable, but would re-add a popped one from .env.
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["TUNNEL_ONDEMAND_ROOT"] = "/tmp/tunnel_ondemand_smoke"   # never the served folder
os.environ["RTBI_MCP_EXPORT_DIR"] = "/tmp/rtbi_mcp_smoke_exports"    # never the real exports / keys
os.environ["RTBI_MCP_KEYS"] = "/tmp/rtbi_mcp_smoke_keys.json"
os.environ["RTBI_MCP_BASE_URL"] = "https://mcp.example.test"

import pandas as pd
from fastmcp import Client

import catalog
import exports
import server
from server import mcp


def exp_path(url: str) -> Path:
    """Where a download_url's file sits on disk (the smoke exports dir)."""
    assert url.startswith("https://mcp.example.test/dl/"), url
    token, name = url.rsplit("/", 2)[-2:]
    return Path(os.environ["RTBI_MCP_EXPORT_DIR"]) / token / name


def hand_monthly_gain(ticker: str) -> pd.Series:
    raw = pd.read_csv(catalog.DATA / "PotDat.csv", sep=";", decimal=",", index_col=0)
    cal = pd.read_csv(catalog.DATA / "Cal.csv", sep=";", decimal=",")
    dates = dict(zip(cal["Daynum"].astype(int), pd.to_datetime(cal["Date"])))
    s = raw.loc[ticker]
    s.index = [dates[int(d)] for d in s.index]
    s = s.sort_index()
    month_end = s.groupby(s.index.to_period("M")).last()
    return (month_end.pct_change() * 100).dropna()


async def main():
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    async with Client(mcp) as c:
        tools = {t.name for t in await c.list_tools()}
        check("tools registered", tools == {"list_datasets", "search_tickers", "get_series",
                                            "plot_series", "get_table", "tunnel_report",
                                            "tunnel_history", "create_api_key"}, str(sorted(tools)))

        r = (await c.call_tool("list_datasets", {})).data
        names = {d["name"] for d in r}
        check("list_datasets", {"PotDat", "longi_price", "Stamdata", "StrategicStocks"} <= names,
              f"{len(r)} datasets")

        r = (await c.call_tool("search_tickers", {"query": "microsoft"})).data
        check("search_tickers", any(h["ticker"] == "MSFT" for h in r), str([h["ticker"] for h in r]))

        r = (await c.call_tool("get_series", {"dataset": "PotDat", "tickers": ["msft", "MU"],
                                              "freq": "M", "transform": "pct_change"})).data
        for t in ("MSFT", "MU"):
            hand = hand_monthly_gain(t)
            got = pd.Series(r["series"][t], index=pd.PeriodIndex(r["dates"], freq="M"))
            common = hand.index.intersection(got.index)
            diff = (hand[common] - got[common]).abs().max()
            check(f"monthly gain {t} == hand", len(common) >= 20 and diff < 1e-3,
                  f"{len(common)} months, max diff {diff:.2e}, latest {got.index[-1]} {got.iloc[-1]:.2f}%")

        check("partial month flagged", r["last_period_partial"] is True, r["dates"][-1])
        r = (await c.call_tool("get_series", {"dataset": "PotDat", "tickers": ["MSFT"], "freq": "M",
                                              "transform": "pct_change", "end": "2026-06"})).data
        check("complete month not flagged", r["last_period_partial"] is False and r["dates"][-1] == "2026-06-30",
              r["dates"][-1])

        r = (await c.call_tool("get_series", {"dataset": "longi_price.csv", "tickers": ["NVDA"],
                                              "start": "2026-09"})).data
        check("get_series daily + start", r["dates"][0] >= "2026-09-01", f"{len(r['dates'])} days")

        # provisional_newest must equal the PotDat gatekeeper's own verdict on the same file
        import potdat_gatekeeper as gatekeeper
        idx = list(catalog.load(catalog.get("PotDat")).index)
        probe = ["MSFT", "^GSPC"] + [next(t for t in idx if t.endswith(s)) for s in (".OL", ".HK", ".T")]
        verdict = gatekeeper.admit(catalog.DATA / "PotDat.csv").carry
        r = (await c.call_tool("get_series", {"dataset": "PotDat", "tickers": probe,
                                              "start": "2026-09"})).data
        expect = [t for t in probe if verdict.carried(t)]
        check("provisional_newest == gatekeeper", r["provisional_newest"] == expect,
              f"{r['provisional_newest']} (carry groups: {','.join(sorted(verdict.groups)) or '-'})")

        r = (await c.call_tool("get_series", {"dataset": "longi_macd_Z", "tickers": ["^AEX"],
                                              "start": "2026-08"})).data
        check("text matrix (macd_Z)", any(v in ("ZOP", "ZNED") for v in r["series"]["^AEX"]))

        r = (await c.call_tool("get_series", {"dataset": "longi_grp_GICS_per20d",
                                              "tickers": ["Tech"], "freq": "W"})).data
        check("sector rows (grp)", len(r["series"]["Tech"]) > 50)

        r = await c.call_tool("plot_series", {"dataset": "longi_price", "tickers": ["MSFT", "MU"],
                                              "freq": "M", "transform": "pct_change",
                                              "start": "2025-10"})
        kinds = [type(b).__name__ for b in r.content]
        img = next((b for b in r.content if type(b).__name__ == "ImageContent"), None)
        check("plot_series", img is not None and img.mimeType == "image/png", str(kinds))
        if img is not None:
            import base64
            out = "/tmp/rtbi_mcp_smoke_plot.png"
            with open(out, "wb") as f:
                f.write(base64.b64decode(img.data))
            print(f"      chart written to {out}")

        r = (await c.call_tool("get_table", {"dataset": "Stamdata", "tickers": ["MSFT"],
                                             "columns": ["Name", "GICS", "Valuta"]})).data
        check("get_table Stamdata", r["rows"][0]["Name"] is not None, str(r["rows"][0]))

        r = (await c.call_tool("get_table", {"dataset": "StrategicStocks"})).data
        check("get_table StrategicStocks", r["rows_total"] > 0, f"{r['rows_total']} picks")

        r = (await c.call_tool("get_table", {"dataset": "StockData2_stacked",
                                             "tickers": ["MSFT"], "limit": 5})).data
        check("get_table stacked history", r["rows_returned"] == 5, f"{r['rows_total']} MSFT rows")

        ten = list(catalog.load(catalog.get("PotDat")).index[:10])
        for args, why, expect in [
                ({"dataset": "nope", "tickers": ["MSFT"]}, "unknown dataset", "Unknown dataset"),
                ({"dataset": "PotDat", "tickers": ["NOTATICKER"]}, "unknown ticker", "Not found"),
                ({"dataset": "Stamdata", "tickers": ["MSFT"]}, "table via get_series", "is a table")]:
            r = await c.call_tool("get_series", args, raise_on_error=False)
            text = r.content[0].text if r.content else ""
            check(f"error: {why}", r.is_error and expect in text, text[:110])

        # over the inline limit: newest dates inline + the COMPLETE frame as a download (no error)
        r = (await c.call_tool("get_series", {"dataset": "PotDat", "tickers": ten})).data
        n_in = len(r["dates"])
        check("get_series over limit = truncated + download",
              r["truncated"] is True and n_in * 10 <= server.MAX_POINTS and "download_url" in r
              and r["download_url"].startswith("https://mcp.example.test/dl/"), f"{n_in} dates inline")
        got = pd.read_csv(exp_path(r["download_url"]), index_col="date")
        check("get_series export is the complete frame",
              len(got) > n_in and list(got.columns) == list(r["series"]) and list(got.index[-n_in:]) == r["dates"]
              and abs(got[ten[0]].iloc[-1] - r["series"][ten[0]][-1]) < 1e-3, f"{len(got)} dates x {got.shape[1]}")
        r = (await c.call_tool("get_series", {"dataset": "longi_price", "tickers": ["MSFT"], "start": "2026-09",
                                              "download": True})).data
        full = pd.read_csv(exp_path(r["download_url"]))
        check("get_series download=true = file + 10-date preview only",
              len(r["dates"]) == 10 and len(full) == r["dates_total"] > 10 and r["tickers_total"] == 1
              and r["truncated"] is True and r["dates"] == list(full["date"].iloc[-10:])
              and "note" in r and "download_url" in r, f"{len(r['dates'])} inline of {len(full)}")
        r = (await c.call_tool("get_series", {"dataset": "PotDat", "tickers": ten, "download": True})).data
        full = pd.read_csv(exp_path(r["download_url"]), index_col="date")
        n_vals = len(r["dates"]) * len(r["series"])
        check("get_series download=true caps tickers x dates in the reply",
              len(r["series"]) == 10 and n_vals <= 100 and full.shape == (r["dates_total"], 10), f"{n_vals} values inline")
        r = (await c.call_tool("get_series", {"dataset": "longi_price", "tickers": ["*"], "freq": "M",
                                              "download": True})).data
        n_vals = len(r["dates"]) * len(r["series"])
        check("get_series ['*'] download=true stays small", n_vals <= 100 and r["tickers_total"] > 1000
              and "download_url" in r, f"{n_vals} values inline, {r['tickers_total']} tickers in the file")
        r = (await c.call_tool("get_series", {"dataset": "longi_price", "tickers": ["MSFT"], "start": "2026-09"})).data
        check("get_series small = inline only", "download_url" not in r and r["truncated"] is False)
        r = (await c.call_tool("get_series", {"dataset": "longi_price", "tickers": ["*"], "freq": "M"})).data
        got = pd.read_csv(exp_path(r["download_url"]), index_col="date")
        check("get_series tickers=['*'] = every row",
              got.shape[1] == len(catalog.load(catalog.get("longi_price")).index), f"{got.shape[1]} tickers")
        r = (await c.call_tool("get_table", {"dataset": "Stamdata", "limit": 5})).data
        got = pd.read_csv(exp_path(r["download_url"]))
        check("get_table over limit = first rows + complete download",
              r["rows_returned"] == 5 and len(got) == r["rows_total"] > 5, f"{len(got)} rows")
        r = (await c.call_tool("get_table", {"dataset": "Stamdata", "tickers": ["MSFT"], "columns": ["Name"],
                                             "download": True})).data
        got = pd.read_csv(exp_path(r["download_url"]))
        check("get_table download=true with selection", len(got) == 1 and list(got.columns) == ["key", "Name"]
              and "note" not in r, str(list(got.columns)))
        r = (await c.call_tool("get_table", {"dataset": "Stamdata", "limit": 200, "download": True})).data
        got = pd.read_csv(exp_path(r["download_url"]))
        check("get_table download=true = 10-row preview + complete file",
              r["rows_returned"] == 10 and len(r["rows"]) == 10 and len(got) == r["rows_total"] > 10
              and "preview only" in r["note"], f"{r['rows_returned']} inline of {len(got)}")

        r = (await c.call_tool("tunnel_report", {"tickers": ["msft", "MU"], "end_date": "2026-09-30",
                                                 "name": "smoke"})).data
        got = {x["ticker"]: x for x in r["rows"]}
        check("tunnel_report rows", set(got) == {"MSFT", "MU"} and got["MSFT"]["end_date"] == "2026-09-30",
              str(got.get("MSFT")))
        check("tunnel_report files", any(f.endswith(".pdf") for f in r["files"])
              and any(f.endswith("_latest.png") for f in r["files"]) and "/smoke_" in r["folder_url"],
              r["folder_url"])
        r = await c.call_tool("tunnel_report", {"tickers": ["NOTATICKER"]}, raise_on_error=False)
        check("error: tunnel_report unknown ticker", r.is_error and "Not found" in r.content[0].text)

        # tunnel_history: compare against a plain pandas read of the CSV
        raw = pd.read_csv(catalog.DATA / "Tunnel" / "history" / "tunnels_history_LB100.csv", sep=";",
                          decimal=",", encoding="utf-8-sig", usecols=[0, 1, 2, 3, 11, 17])
        raw.columns = ["daynum", "ticker", "status", "length_td", "end_date", "close_pos"]
        want = int(((raw.status == "tunnel") & (raw.length_td >= 60) & (raw.close_pos >= 0.9)).sum())
        r = (await c.call_tool("tunnel_history", {"where": ["status = tunnel", "length_td >= 60",
                                                            "close_pos >= 0.9"], "limit": 5})).data
        check("tunnel_history cross-history filter", r["rows_matched"] == want
              and r["rows_returned"] == min(5, want) and ("note" in r) == (want > 5),
              f"{r['rows_matched']} matched vs {want} by hand")
        sel = raw[(raw.status == "tunnel") & (raw.length_td >= 60) & (raw.close_pos >= 0.9)]
        check("tunnel_history truncated = newest rows + full export",
              r["rows"][-1][0] == sel.end_date.max() and r["rows"][0][0] <= r["rows"][-1][0]
              and r["download_url"].endswith(f"tunnel_history_{want}rows.csv"), r["download_url"][-60:])
        exp = exp_path(r["download_url"])
        full = pd.read_csv(exp)
        check("tunnel_history export is the complete match", len(full) == want and list(full.columns) == r["columns"]
              and (full.close_pos >= 0.9).all(), f"{len(full)} rows in {exp.name}")
        r = (await c.call_tool("tunnel_history", {"tickers": ["msft"], "limit": 500})).data
        n = int((raw.ticker == "MSFT").sum())
        check("tunnel_history one ticker", r["rows_matched"] == n and r["rows_returned"] == min(n, 500)
              and r["rows"][0][0] <= r["rows"][-1][0], f"{n} MSFT rows")
        r = (await c.call_tool("tunnel_history", {"summarize": "month", "where": ["status = tunnel"]})).data
        by_status = int((raw.status == "tunnel").sum())
        check("tunnel_history summarize", sum(row[1] for row in r["rows"]) == by_status == r["rows_matched"],
              f"{r['groups']} months, {by_status} tunnel rows")
        r = (await c.call_tool("tunnel_history", {"tickers": ["MSFT"], "limit": 2})).data
        check("tunnel_history core columns", r["columns"] == ["end_date", "ticker", "status", "length_td",
              "width_pct", "slope20_pct", "close_pos"], str(r["columns"]))
        r = (await c.call_tool("tunnel_history", {"tickers": ["MSFT"], "limit": 2, "extended": True,
                                                  "columns": ["end_date", "supports_upper", "last_close"],
                                                  "where": ["supports_upper >= 2"]})).data
        check("tunnel_history extended", r["rows_returned"] == 2 and r["columns"][1] == "supports_upper",
              str(r["rows"]))
        for args, why, expect in [({"columns": ["last_close"]}, "extended column w/o flag", "extended=true"),
                                  ({"where": ["supports_upper > 1"]}, "extended filter w/o flag", "extended=true"),
                                  ({"where": ["nonsense"]}, "bad filter", "Cannot read filter"),
                                  ({"where": ["foo > 1"]}, "unknown column", "Unknown column"),
                                  ({"tickers": ["NOTATICKER"]}, "unknown ticker", "Not in the tunnel history"),
                                  ({"summarize": "date"}, "too many groups", "groups")]:
            r = await c.call_tool("tunnel_history", args, raise_on_error=False)
            text = r.content[0].text if r.content else ""
            check(f"error: tunnel_history {why}", r.is_error and expect in text, text[:110])

        res = await c.read_resource("potentials://conventions")
        check("conventions resource", "seven-pack" in res[0].text)

    # Allowlist: fake the identity Google would have proven, then call through the middleware.
    from types import SimpleNamespace
    server.ALLOWED.clear()
    server.ALLOWED.add("allowed@example.com")
    mcp.add_middleware(server.AllowlistMiddleware())
    for email, should_pass in [("allowed@example.com", True), ("ALLOWED@example.com", True),
                               ("stranger@example.com", False), (None, False)]:
        server.get_access_token = (lambda e=email: SimpleNamespace(claims={"email": e}) if e else None)
        try:
            async with Client(mcp) as c:
                r = await c.call_tool("list_datasets", {}, raise_on_error=False)
                passed = not r.is_error
        except Exception:
            passed = False
        check(f"allowlist {email}", passed == should_pass, "let in" if passed else "refused")

    # API keys + the authenticated /dl/ route (members and strangers; revoked / removed members)
    import shutil
    from starlette.testclient import TestClient
    shutil.rmtree(os.environ["RTBI_MCP_EXPORT_DIR"], ignore_errors=True)
    Path(os.environ["RTBI_MCP_KEYS"]).unlink(missing_ok=True)

    server.get_access_token = lambda: None          # the tool itself (the middleware would refuse earlier)
    try:
        getattr(server.create_api_key, "fn", server.create_api_key)()
        refused = False
    except Exception as exc:
        refused = "signed-in" in str(exc)
    check("create_api_key refused without identity", refused and not Path(os.environ["RTBI_MCP_KEYS"]).exists())

    server.get_access_token = lambda: SimpleNamespace(claims={"email": "Allowed@Example.com"})
    async with Client(mcp) as c:
        key1 = (await c.call_tool("create_api_key", {})).data["api_key"]
        made = (await c.call_tool("create_api_key", {})).data
        key2 = made["api_key"]
    check("create_api_key: copy-paste store commands carry the key",
          all(key2 in made["store_it"][k] for k in ("linux", "macos", "windows"))
          and "\"Authorization: Bearer $POTENTIALS_KEY\"" in made["use"])
    check("create_api_key: owner found, re-issue replaces",
          exports.owner_of(key2) == "allowed@example.com" and exports.owner_of(key1) is None and key1 != key2)
    stored = Path(os.environ["RTBI_MCP_KEYS"]).read_text()
    check("key store holds a hash, not the key", key2 not in stored
          and oct(Path(os.environ["RTBI_MCP_KEYS"]).stat().st_mode & 0o777) == "0o600", "mode 600")

    link = exports.write_csv(pd.DataFrame({"a": [1.5, 2.5]}), "probe")["download_url"]
    url = link.replace("https://mcp.example.test", "")
    web = TestClient(mcp.http_app(path="/mcp"))
    server._allowed_now = lambda: {"allowed@example.com"}
    bearer = {"Authorization": f"Bearer {key2}"}

    token_dir = exp_path(link).parent
    check("export stamped with its owner", (token_dir / exports.OWNER_FILE).read_text() == "allowed@example.com")
    r = web.get(url)
    check("download: link alone, owner allowed = 200 + the file",
          r.status_code == 200 and r.text.strip().splitlines() == ["a", "1.5", "2.5"], str(r.status_code))
    check("download: .owner file is not served", web.get(url.rsplit("/", 1)[0] + "/.owner").status_code in (400, 404))
    check("download: wrong key = 401 (not ignored)", web.get(url, headers={"Authorization": "Bearer pk_nope"}).status_code == 401)
    check("download: old (replaced) key = 401", web.get(url, headers={"Authorization": f"Bearer {key1}"}).status_code == 401)
    r = web.get(url, headers=bearer)
    check("download: member key = 200 + the file", r.status_code == 200 and r.text.strip().splitlines() == ["a", "1.5", "2.5"],
          str(r.status_code))
    check("download: X-API-Key header works too", web.get(url, headers={"X-API-Key": key2}).status_code == 200)
    check("download: unknown token = 404", web.get("/dl/AAAAAAAAAAAAAAAA/probe.csv", headers=bearer).status_code == 404)
    check("download: path tricks = 404/400", all(web.get(p, headers=bearer).status_code in (400, 404)
          for p in (url.rsplit("/", 1)[0] + "/..%2Fprobe.csv", url.rsplit("/", 2)[0] + "/../../etc/passwd")))
    old = os.stat(exp_path(link)).st_mtime
    os.utime(exp_path(link), (old - 25 * 3600, old - 25 * 3600))
    check("download: expired = 404", web.get(url, headers=bearer).status_code == 404)
    os.utime(exp_path(link), (old, old))
    server._allowed_now = lambda: set()
    check("download: member removed from allowlist = 401 at once (key and link)",
          web.get(url, headers=bearer).status_code == 401 and web.get(url).status_code == 401)
    server._allowed_now = lambda: {"allowed@example.com"}
    check("download: back on the list = 200", web.get(url, headers=bearer).status_code == 200
          and web.get(url).status_code == 200)
    server._allowed_now = lambda: {"allowed@example.com", "other@example.com"}
    server.get_access_token = lambda: SimpleNamespace(claims={"email": "other@example.com"})
    other = exports.write_csv(pd.DataFrame({"b": [1]}), "other")["download_url"].replace("https://mcp.example.test", "")
    server._allowed_now = lambda: {"allowed@example.com"}
    check("download: link follows ITS owner (other removed = 401, allowed's key still works)",
          web.get(other).status_code == 401 and web.get(other, headers=bearer).status_code == 200)
    server.get_access_token = lambda: None
    orphan = exports.write_csv(pd.DataFrame({"c": [1]}), "orphan")["download_url"].replace("https://mcp.example.test", "")
    check("download: link without owner needs a key", web.get(orphan).status_code == 401
          and web.get(orphan, headers=bearer).status_code == 200)
    check("revoke", exports.revoke("allowed@example.com") and web.get(url, headers=bearer).status_code == 401
          and web.get(url).status_code == 200)
    shutil.rmtree(os.environ["RTBI_MCP_EXPORT_DIR"], ignore_errors=True)
    Path(os.environ["RTBI_MCP_KEYS"]).unlink(missing_ok=True)

    print(f"\n{'ALL PASS' if not failures else f'{failures} FAILED'}")
    return failures


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
