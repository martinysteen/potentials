"""
smoke_test.py - exercise every tool through FastMCP's in-memory client (no HTTP,
no auth), and check the monthly gain against a hand computation from PotDat.csv.

    cd ~/potentials/repositoryRTBI/mcp && python smoke_test.py
"""
import asyncio
import os

os.environ.pop("GOOGLE_CLIENT_ID", None)   # in-memory: test the tools, not the auth

import pandas as pd
from fastmcp import Client

import catalog
from server import mcp


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
                                            "plot_series", "get_table"}, str(sorted(tools)))

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
                ({"dataset": "Stamdata", "tickers": ["MSFT"]}, "table via get_series", "is a table"),
                ({"dataset": "PotDat", "tickers": ten}, "row cap", "values requested")]:
            r = await c.call_tool("get_series", args, raise_on_error=False)
            text = r.content[0].text if r.content else ""
            check(f"error: {why}", r.is_error and expect in text, text[:110])

        res = await c.read_resource("potentials://conventions")
        check("conventions resource", "seven-pack" in res[0].text)

    # Allowlist: fake the identity Google would have proven, then call through the middleware.
    import server
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

    print(f"\n{'ALL PASS' if not failures else f'{failures} FAILED'}")
    return failures


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
