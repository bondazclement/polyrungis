#!/usr/bin/env python3
"""Addendum — asymétrie de latence (données collecte ETH).
Mesure : (1) cadence de rafraîchissement des flux (intervalle entre mises à
jour), (2) latence de réception (recv − horodatage serveur), (3) amplitude
de l'erreur permanente du carnet (de combien l'ask bouge entre deux updates).
Usage : addendum_latence.py <journal_dir>
"""
import json, glob, sys, statistics as st
import numpy as np

D = sys.argv[1]
def pct(v, q):
    v = sorted(v); return v[min(len(v)-1, int(q*len(v)))] if v else float("nan")

# Par token : derniers recv/ask pour intervalles + deltas ; latences de réception.
last_recv = {}; last_ask = {}
inter = {}         # token -> [intervalles ms entre updates de best_ask]
delta = {}         # token -> [|Δ best_ask| entre updates]
lat_clob = []; lat_oracle = []; oracle_gap = []
last_oracle = None

for f in sorted(glob.glob(f"{D}/journal_*.ndjson")):
    for line in open(f, errors="replace"):
        if '"stream"' not in line: continue
        try: fr = json.loads(line)
        except: continue
        s = fr.get("stream"); recv = fr.get("recv_ms", 0); raw = fr.get("raw", "")
        if s == "clob" and "price_changes" in raw:
            try: m = json.loads(raw)
            except: continue
            ts = m.get("timestamp")
            if ts: lat_clob.append(recv - int(ts))
            for ch in m.get("price_changes", []):
                tk = ch["asset_id"][:12]; a = ch.get("best_ask")
                if not a: continue
                a = float(a)
                if tk in last_ask and a != last_ask[tk]:
                    inter.setdefault(tk, []).append(recv - last_recv[tk])  # entre CHANGEMENTS de prix
                    delta.setdefault(tk, []).append(abs(a - last_ask[tk]))
                    last_recv[tk] = recv
                elif tk not in last_ask:
                    last_recv[tk] = recv
                last_ask[tk] = a
        elif s == "rtds" and '"eth/usd"' in raw:
            try:
                p = json.loads(raw); ext = p.get("timestamp"); pay = p["payload"]["timestamp"]
                if ext: lat_oracle.append(recv - int(ext))
                if last_oracle is not None: oracle_gap.append(int(pay) - last_oracle)
                last_oracle = int(pay)
            except: pass

allinter = [x for v in inter.values() for x in v if 0 < x < 30000]
alldelta = [x for v in delta.values() for x in v]
print("══ ASYMÉTRIE DE LATENCE — données ETH ══\n")
print("1) Cadence des VRAIS changements de prix (best_ask) — la métrique de l'asymétrie")
print(f"   médiane {int(st.median(allinter))} ms   p75 {pct(allinter,.75):.0f} ms   p90 {pct(allinter,.9):.0f} ms   (n={len(allinter)})")
print(f"   → entre deux changements le carnet du bot est FIGÉ ; sur la queue (p90 ~1,5 s) le")
print(f"     prix affiché peut être très en retard sur le fair (oracle qui bouge chaque seconde)")
print("\n2) Cadence de l'oracle Chainlink (intervalle source entre ticks eth/usd)")
print(f"   médiane {int(st.median(oracle_gap))} ms   p90 {pct(oracle_gap,.9):.0f} ms")
print("\n3) Latence de réception (recv − horodatage serveur)")
print(f"   CLOB   : médiane {int(st.median(lat_clob))} ms   p90 {pct(lat_clob,.9):.0f} ms   (n={len(lat_clob)})")
print(f"   Oracle : médiane {int(st.median(lat_oracle))} ms   p90 {pct(lat_oracle,.9):.0f} ms  (réseau+relais)")
print("\n4) Amplitude de l'erreur permanente (|Δ best_ask| entre deux updates du carnet)")
print(f"   médiane {st.median(alldelta):.3f}   p90 {pct(alldelta,.9):.3f}   p99 {pct(alldelta,.99):.3f}   (n={len(alldelta)})")
big = sum(1 for x in alldelta if x >= 0.02)/len(alldelta)*100
print(f"   sauts ≥ 0,02 (2 cents) entre deux updates : {big:.1f}% des changements")
print("\n── Lecture ──")
print("   Le carnet du bot est rafraîchi à cette cadence : entre deux updates il ne")
print("   bouge pas alors que le marché, lui, bouge. L'ordre de grandeur du 'décalage")
print("   permanent' = cadence/2 (âge moyen du carnet) × vitesse de mouvement.")
