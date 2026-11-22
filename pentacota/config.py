import json, os, copy
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

def _merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            _merge(a[k], v)
        else:
            a[k] = v
    return a

def load():
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    p = os.path.join(ROOT, "config.local.json")   # optional private overrides
    if os.path.exists(p):
        with open(p) as f:
            _merge(cfg, json.load(f))
    return copy.deepcopy(cfg)
