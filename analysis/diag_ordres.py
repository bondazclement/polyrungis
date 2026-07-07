#!/usr/bin/env python3
"""Diagnostic du passage d'ordre taker (délai 250 ms).
Pour chaque décision réelle du micro-test : comment l'ask du token visé a
bougé pendant le délai, et quelle limite aurait rempli l'ordre.
Usage : diag_ordres.py <run_live_dir>
"""
import json, glob, re, sys, bisect
from datetime import datetime

D = sys.argv[1]
LOG = f"{D}/run.log"

def ts_ms(iso):  # "2026-07-07T01:59:12.377731Z" -> epoch ms
    return int(datetime.strptime(iso[:26], "%Y-%m-%dT%H:%M:%S.%f").timestamp() * 1000)

def strip(l):
    return re.sub(r"\x1b\[[0-9;]*m", "", l)

# 1) Décisions + résultats depuis le log
orders = []  # (ts, side, ask, avg, tau, dist, result, fill)
pend = None
for l in open(LOG, errors="replace"):
    l = strip(l)
    m = re.search(r"(\S+Z)\s+INFO pm_bot: TAKER: (UP|DOWN) \(z=([-\d.]+) p=([\d.]+) ask=([\d.]+) avg=([\d.]+) tau=(\d+)s dist=(\d+)", l)
    if m:
        if pend: orders.append(pend)
        pend = dict(ts=ts_ms(m.group(1)), side=m.group(2), z=float(m.group(3)), p=float(m.group(4)),
                    ask=float(m.group(5)), avg=float(m.group(6)), tau=int(m.group(7)), dist=int(m.group(8)),
                    result="?", fill=None)
        continue
    if pend and "ENTRÉE EXÉCUTÉE" in l:
        f = re.search(r"@ ([\d.]+)", l); pend["result"]="EXÉCUTÉE"; pend["fill"]=float(f.group(1)) if f else None
        orders.append(pend); pend=None
    elif pend and ("ÉCHEC ORDRE" in l or "NON EXÉCUTÉE" in l):
        pend["result"]="ÉCHEC"; orders.append(pend); pend=None
if pend: orders.append(pend)
print(f"{len(orders)} décisions dans {D}")

# 2) Fenêtres (gamma) : map temps -> token_up/down
wins = []  # (start_ms, end_ms, token_up8, token_down8)
for f in sorted(glob.glob(f"{D}/journal_*.ndjson")):
    for line in open(f, errors="replace"):
        if '"gamma"' not in line: continue
        try:
            fr = json.loads(line); w = json.loads(fr["raw"])
            wins.append((w["start_ms"], w["end_ms"], w["token_up"][:12], w["token_down"][:12]))
        except Exception: pass
wins.sort()

def token_for(ts, side):
    for s, e, up, dn in wins:
        if s <= ts < e + 200000:
            return (up if side == "UP" else dn)
    return None

# 3) Tokens et fenêtres temporelles à extraire
besoin = {}  # token8 -> list of (t0,t1)
for o in orders:
    tk = token_for(o["ts"], o["side"]); o["token"] = tk
    if tk: besoin.setdefault(tk, []).append((o["ts"]-2000, o["ts"]+2500))

# 4) Série best_ask de ces tokens dans ces fenêtres
asks = {tk: [] for tk in besoin}  # token -> [(recv_ms, best_ask)]
for f in sorted(glob.glob(f"{D}/journal_*.ndjson")):
    for line in open(f, errors="replace"):
        if '"clob"' not in line or "price_changes" not in line: continue
        try: fr = json.loads(line)
        except: continue
        rm = fr.get("recv_ms", 0); raw = fr.get("raw", "")
        for tk, plages in besoin.items():
            if tk not in raw: continue
            if not any(a <= rm <= b for a, b in plages): continue
            try:
                m = json.loads(raw)
                for ch in m.get("price_changes", []):
                    if ch["asset_id"][:12] == tk and ch.get("best_ask"):
                        asks[tk].append((rm, float(ch["best_ask"])))
            except Exception: pass
for tk in asks: asks[tk].sort()

def ask_at(tk, t):
    s = asks.get(tk, [])
    if not s: return None
    i = bisect.bisect_right([x[0] for x in s], t) - 1
    return s[i][1] if i >= 0 else None

def ask_min_window(tk, t0, t1):  # meilleure (plus basse) ask disponible pendant le délai
    s = [a for r, a in asks.get(tk, []) if t0 <= r <= t1]
    return min(s) if s else None

# 5) Rapport
print(f"\n{'τ':>4} {'côté':>4} {'résultat':>9} {'ask déc.':>8} {'ask+250':>8} {'ask+500':>8} {'ask+1s':>7} {'limite envoyée':>14} {'ask min 250ms':>13}")
for o in sorted(orders, key=lambda x: x["tau"]):
    tk = o["token"]
    a0 = ask_at(tk, o["ts"]); a250 = ask_at(tk, o["ts"]+250); a500 = ask_at(tk, o["ts"]+500); a1 = ask_at(tk, o["ts"]+1000)
    amin = ask_min_window(tk, o["ts"], o["ts"]+250)
    limite = min(o["avg"]+0.01, 0.99)  # limit_price actuel du taker
    fmt = lambda x: f"{x:.3f}" if x is not None else "  —  "
    print(f"{o['tau']:>4} {o['side']:>4} {o['result']:>9} {fmt(a0):>8} {fmt(a250):>8} {fmt(a500):>8} {fmt(a1):>7} {limite:>14.3f} {fmt(amin):>13}")

# 6) Synthèse : mouvement d'ask pendant 250 ms, exécutés vs échoués
import statistics as st
def bougé(sel):
    d = []
    for o in sel:
        a0 = ask_at(o["token"], o["ts"]); a250 = ask_at(o["token"], o["ts"]+250)
        if a0 is not None and a250 is not None: d.append(a250 - a0)
    return d
exe = bougé([o for o in orders if o["result"]=="EXÉCUTÉE"])
ech = bougé([o for o in orders if o["result"]=="ÉCHEC"])
print("\n── Mouvement de l'ask pendant le délai (ask@+250 − ask@décision) ──")
if exe: print(f"  exécutés : médiane {st.median(exe):+.4f}  (n={len(exe)})")
if ech: print(f"  échoués  : médiane {st.median(ech):+.4f}  (n={len(ech)})")
print("\n── τ des exécutés vs échoués ──")
print(f"  exécutés : {sorted(o['tau'] for o in orders if o['result']=='EXÉCUTÉE')}")
print(f"  échoués  : {sorted(o['tau'] for o in orders if o['result']=='ÉCHEC')}")
