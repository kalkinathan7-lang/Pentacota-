from dataclasses import dataclass

@dataclass
class RiskSettings:
    risk_pct: float = 0.5
    max_positions: int = 2
    daily_loss_pct: float = 2.0
    min_rr: float = 1.8

def position_size(equity: float, entry: float, stop: float, risk_pct: float = 0.5) -> float:
    if min(equity, entry, stop) <= 0 or entry == stop:
        return 0.0
    risk_cash = equity * risk_pct / 100.0
    return risk_cash / abs(entry - stop)
