import streamlit as st
import pandas as pd
from pentacota import config, paper as P, backtest
from pentacota.scanner import Scanner

st.set_page_config(page_title="Pentacota", layout="wide")

@st.cache_resource
def get_scanner():
    return Scanner(config.load())

sc = get_scanner()
st.title("Pentacota")
st.caption("Paper mode. Valid setups only; live trading is locked.")

c1, c2, c3 = st.columns(3)
if c1.button("Stop scanner" if sc.running else "Start scanner", type="primary"):
    sc.stop() if sc.running else sc.start()
    st.rerun()
kill = P.kill_active()
if c2.button("Release kill switch" if kill else "Kill switch"):
    P.set_kill(not kill)
    if not kill: sc.paper.flatten(sc.prices)
    st.rerun()
if c3.button("Reset paper account"):
    sc.paper.reset(); st.rerun()

@st.fragment(run_every=5)
def live():
    s = sc.snapshot(); a = s["account"]
    st.write(f"Scanner **{'running' if s['running'] else 'stopped'}**" + (f" | kill switch ON" if a["kill"] else "") +
             (f" | error: {s['error']}" if s["error"] else ""))
    m = st.columns(6)
    for col, (k, v) in zip(m, [("Coins scanned", s["scanned"]), ("Valid setups", s["valid"]), ("Waiting", s["waiting"]),
                               ("Active positions", len(a["positions"])), ("Equity", f"{a['equity']:,.2f}"),
                               ("Day PnL", f"{a['day_pnl_pct']:.2f}%")]):
        col.metric(k, v)
    b = s["btc"]
    if b: st.write(f"BTC 1H: **{b['state']}** (RSI {b['rsi']:.1f})")
    if not s["rows"]:
        st.info("Press Start scanner. The first scan takes about a minute."); return
    df = pd.DataFrame(s["rows"])[["symbol", "price", "trend", "rsi", "volume", "score", "status", "reason"]]
    st.dataframe(df, use_container_width=True, hide_index=True, height=420)
    sym = st.selectbox("Setup detail", [r["symbol"] for r in s["rows"]])
    d = sc.detail.get(sym)
    if d:
        st.subheader(f"{sym}: {d['status']} (score {d['score']})"); st.write(d["reason"])
        if d.get("plan"):
            p = d["plan"]
            st.table(pd.DataFrame({"Entry": [p["entry"]], "Stop": [p["sl"]], "Target": [p["tp"]], "R/R": [p["rr"]],
                                   "Size": [p["units"]], "Risk amt": [p["risk_amt"]]}))
            st.caption("Target basis: " + p["tp_basis"]); st.write("Invalidated if:", d["invalidation"])
        st.write("Checks"); st.table(pd.DataFrame(d["checks"])) if d["checks"] else None
        st.write("Indicators", d["ind"])
    st.subheader("Active positions")
    st.dataframe(pd.DataFrame(a["positions"]) if a["positions"] else pd.DataFrame({"none": []}), use_container_width=True)
    st.subheader("Closed paper trades")
    if a["closed"]: st.dataframe(pd.DataFrame(a["closed"])[["symbol", "dir", "entry", "exit", "why", "pnl", "r"]], use_container_width=True)
live()

with st.expander("Backtest"):
    syms = st.text_input("Symbols (comma separated, max 5)", "BTC,ETH")
    if st.button("Run backtest"):
        with st.spinner("Running..."):
            for x in [t.strip().upper() for t in syms.split(",") if t.strip().isalnum()][:5]:
                try:
                    r = backtest.run(x, sc.cfg); lst = r.pop("list"); st.write(r)
                except Exception as e: st.error(f"{x}: {e}")
