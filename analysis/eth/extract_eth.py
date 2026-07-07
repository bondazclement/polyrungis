#!/usr/bin/env python3
"""Extracteur ETH HAUTE PRÉCISION (data_collect/eth_*).
Sur ETH les écarts se jouent au centime : on utilise EXCLUSIVEMENT
full_accuracy_value (entier ×1e18) pour le strike, le spot et l'écart —
jamais la valeur arrondie. Produit analysis/eth/out/{ticks,spot,tops,windows}.csv
"""
import glob, io, json, os, subprocess, sys
BASE=os.path.dirname(os.path.abspath(__file__)); OUT=f"{BASE}/out"; os.makedirs(OUT, exist_ok=True)
SCALE=10**18  # eth/usd full_accuracy : 18 décimales

def frames(path):
    if path.endswith(".zst"):
        p=subprocess.Popen(["zstdcat",path],stdout=subprocess.PIPE); f=io.TextIOWrapper(p.stdout,errors="replace")
    else: f=open(path,errors="replace")
    for l in f:
        try: yield json.loads(l)
        except json.JSONDecodeError: pass
    f.close()

def main(patterns):
    paths=sorted(set(sum((glob.glob(p) for p in patterns),[])))
    print(f"{len(paths)} journaux", file=sys.stderr)
    seen_t=set(); seen_s=set(); windows={}; last_top={}; nf=0
    ft=open(f"{OUT}/ticks.csv","w"); fs=open(f"{OUT}/spot.csv","w"); fb=open(f"{OUT}/tops.csv","w")
    ft.write("ts_ms,price\n"); fs.write("ts_ms,price\n"); fb.write("recv_ms,asset,bid,ask\n")
    for path in paths:
        for fr in frames(path):
            nf+=1; st=fr.get("stream"); raw=fr.get("raw",""); rm=fr.get("recv_ms",0)
            if st=="rtds":
                if '"eth/usd"' in raw:  # STRIKE/VOL : precision maximale
                    try:
                        p=json.loads(raw)["payload"]; ts=int(p["timestamp"])
                        if ts not in seen_t:
                            seen_t.add(ts); ft.write(f"{ts},{int(p['full_accuracy_value'])/SCALE:.10f}\n")
                    except Exception: pass
                elif '"ethusdt"' in raw:  # relais spot (moins précis, informatif)
                    try:
                        p=json.loads(raw)["payload"]; ts=int(p["timestamp"])
                        if ts not in seen_s:
                            seen_s.add(ts); fs.write(f"{ts},{p['value']}\n")
                    except Exception: pass
            elif st=="clob" and '"price_changes"' in raw:
                try:
                    m=json.loads(raw); sec=rm//1000
                    for ch in m.get("price_changes",[]):
                        a=ch["asset_id"][:12]; bid=ch.get("best_bid"); ask=ch.get("best_ask")
                        if not bid or not ask: continue
                        prev=last_top.get(a)
                        if prev and prev==(sec,bid,ask): continue
                        last_top[a]=(sec,bid,ask); fb.write(f"{rm},{a},{bid},{ask}\n")
                except Exception: pass
            elif st=="gamma":
                try:
                    m=json.loads(raw); windows[m["slug"]]=(m["slug"],m["start_ms"],m["end_ms"],m["token_up"][:12],m["token_down"][:12])
                except Exception: pass
    ft.close(); fs.close(); fb.close()
    with open(f"{OUT}/windows.csv","w") as fw:
        fw.write("slug,t0_ms,end_ms,token_up,token_down\n")
        for w in sorted(windows.values(),key=lambda x:x[1]): fw.write(",".join(map(str,w))+"\n")
    print(f"{nf} trames | {len(seen_t)} ticks eth/usd | {len(seen_s)} spot | {len(windows)} fenêtres", file=sys.stderr)

if __name__=="__main__": main(sys.argv[1:])
