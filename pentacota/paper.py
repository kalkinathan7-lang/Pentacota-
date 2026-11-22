from pathlib import Path
import pandas as pd

FILE = Path("paper_trades.csv")
COLUMNS = ["timestamp","symbol","direction","entry","stop_loss","take_profit","quantity","status","notes"]

def read_log():
    if FILE.exists():
        try: return pd.read_csv(FILE)
        except Exception: pass
    return pd.DataFrame(columns=COLUMNS)

def add_trade(signal: dict):
    plan = signal.get("plan") or {}
    if not plan: raise ValueError("Signal has no validated plan")
    row = {"timestamp":pd.Timestamp.utcnow().isoformat(),"symbol":signal["symbol"],"direction":signal["direction"],"entry":plan["entry"],"stop_loss":plan["stop_loss"],"take_profit":plan["take_profit"],"quantity":plan["quantity"],"status":"OPEN","notes":"Manual paper entry; simulated fill not verified"}
    df=read_log(); df=pd.concat([df,pd.DataFrame([row])],ignore_index=True); df.to_csv(FILE,index=False)

def close_trade(index: int, exit_price: float):
    df=read_log()
    if index < 0 or index >= len(df): raise IndexError("Trade index invalid")
    df.loc[index,"status"]="CLOSED"
    df.loc[index,"notes"] = str(df.loc[index,"notes"]) + f" | manual exit={exit_price}"
    df.to_csv(FILE,index=False)
