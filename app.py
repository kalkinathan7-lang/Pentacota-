from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pentacota.data import get_top_usdt_universe, scan_market, get_candles
from pentacota.strategy import analyze
from pentacota.paper import read_log, add_trade

st.set_page_config(page_title="PENTACOTA", page_icon="🧭", layout="wide")
st.title("🧭 PENTACOTA")
st.caption("Crypto Trading Intelligence • Market data scanner • Paper-only prototype")
st.warning("Prototype: public CoinDCX spot data only. No live orders. Signals are not validated profitability claims.")

with st.sidebar:
    st.header("Scanner settings")
    equity = st.number_input("Paper account equity (USDT equivalent)", min_value=100.0, value=10000.0, step=500.0)
    risk_pct = st.slider("Risk per trade (%)", 0.1, 1.0, 0.5, 0.1)
    min_rr = st.slider("Minimum reward/risk", 1.2, 3.0, 1.8, 0.1)
    max_coins = st.selectbox("Scan universe", [10, 25, 50], index=2)
    scan_button = st.button("🔍 Scan market", type="primary", use_container_width=True)
    st.caption("Scanner stops when you close the app. No background process or order execution.")

if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "scan_time" not in st.session_state: st.session_state.scan_time = None
if scan_button:
    with st.spinner("Fetching ticker and market metadata…"):
        try:
            universe = get_top_usdt_universe(max_coins)
            if not universe: st.error("No eligible USDT markets mapped. CoinDCX API response or market mapping may have changed.")
            else:
                progress = st.progress(0, text="Fetching candles…")
                raw = scan_market(universe, lambda done,total: progress.progress(done/max(total,1), text=f"Fetching candles: {done}/{total}"))
                btc = next((r["1h"] for r in raw if r["coin"]["symbol"] == "BTC" and r["error"] is None), None)
                analyzed=[]
                for r in raw:
                    if r["error"]:
                        analyzed.append({"symbol":r["coin"]["symbol"],"price":r["coin"]["price"],"status":"NO TRADE","direction":None,"score":0,"reason":"Data unavailable: " + r["error"],"details":{},"plan":None,"volume_24h":r["coin"]["volume_24h"],"change_24h":r["coin"]["change_24h"]})
                    else:
                        s=analyze(r["coin"],r["1h"],r["15m"],btc,equity,risk_pct,min_rr)
                        s["volume_24h"]=r["coin"]["volume_24h"];s["change_24h"]=r["coin"]["change_24h"]
                        analyzed.append(s)
                rank={"LONG":4,"SHORT":4,"WAITING":2,"NO TRADE":1}
                analyzed.sort(key=lambda x:(rank.get(x["status"],0),x["score"]),reverse=True)
                st.session_state.scan_results=analyzed;st.session_state.scan_time=pd.Timestamp.utcnow()
                progress.empty()
        except Exception as e:
            st.error(f"Scanner error: {e}")

results=st.session_state.scan_results
if results:
    valid=sum(x["status"] in ("LONG","SHORT") for x in results)
    waiting=sum(x["status"]=="WAITING" for x in results)
    active=sum(x["status"] in ("LONG","SHORT") for x in results)
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Coins scanned",len(results));c2.metric("Valid setups",valid);c3.metric("Waiting",waiting);c4.metric("Paper positions",len(read_log().query("status == 'OPEN'")))
    st.caption(f"Last scan: {st.session_state.scan_time}")
    display=pd.DataFrame([{ "Coin":x["symbol"],"Price":x["price"],"Trend":x.get("details",{}).get("1h trend","—"),"RSI":x.get("details",{}).get("15m RSI","—"),"Volume 24h":x.get("volume_24h",0),"Score":x["score"],"Status":x["status"],"Reason":x["reason"]} for x in results])
    st.subheader("Scanner")
    st.dataframe(display,hide_index=True,use_container_width=True)
    symbols=[x["symbol"] for x in results]
    selected=st.selectbox("Select coin for details",symbols)
    s=next(x for x in results if x["symbol"]==selected)
    st.subheader(f"{s['symbol']} — {s['status']}")
    st.write(s["reason"])
    if s.get("details"):
        st.json(s["details"])
    if s.get("plan"):
        p=s["plan"]
        cols=st.columns(5)
        cols[0].metric("Entry",f"{p['entry']:.8g}");cols[1].metric("Stop loss",f"{p['stop_loss']:.8g}");cols[2].metric("Take profit",f"{p['take_profit']:.8g}");cols[3].metric("R:R",f"{p['risk_reward']:.2f}");cols[4].metric("Quantity",f"{p['quantity']:.6g}")
        st.write("**Invalidation:**",p["invalidation"])
        if st.button("Add to paper trade log",key="paper_"+s["symbol"]):
            try: add_trade(s);st.success("Added to local paper log.")
            except Exception as e: st.error(str(e))
    else:
        st.info("No trade plan is available. This status is not an entry recommendation.")
    st.subheader("Market context chart")
    try:
        coin=next((r for r in results if r["symbol"]==selected),None)
        pair=None
        # Pair stored in last universe only during current scan; reconstruct known spot format.
        pair=f"B-{selected}_USDT"
        candles=get_candles(pair,"15m",200)
        fig=go.Figure(data=[go.Candlestick(x=candles.time,open=candles.open,high=candles.high,low=candles.low,close=candles.close,name="15m")])
        fig.update_layout(height=450,xaxis_rangeslider_visible=False)
        st.plotly_chart(fig,use_container_width=True)
    except Exception as e: st.caption(f"Chart unavailable: {e}")
else:
    st.info("No scan results yet. Press **Scan market** to fetch live public data.")

st.divider();st.subheader("Paper trade log")
log=read_log()
if len(log): st.dataframe(log,use_container_width=True,hide_index=True)
else: st.caption("No paper trades recorded yet.")
st.caption("Risk controls shown are planning defaults only. Daily loss and open-position limits are not enforced against live accounts in this prototype.")
