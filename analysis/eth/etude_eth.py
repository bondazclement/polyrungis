#!/usr/bin/env python3
"""Modèle ETH — nature du processus + frontière d'efficience (en DOLLARS).
Reproduit la démarche BTC (études 1 & 6) sur les 6 h de collecte ETH, mais
à l'échelle du dollar (ETH ~1780 $ : les écarts se jouent en $, pas en
dizaines de $). Précision : full_accuracy (ticks.csv 10 décimales).
"""
import numpy as np, pandas as pd
from scipy.stats import norm

OUT = "analysis/eth/out"
HL = 60.0
tk = pd.read_csv(f"{OUT}/ticks.csv").drop_duplicates("ts_ms").sort_values("ts_ms")
win = pd.read_csv(f"{OUT}/windows.csv").sort_values("t0_ms")
tops = pd.read_csv(f"{OUT}/tops.csv")
ts = tk.ts_ms.to_numpy(); px = tk.price.to_numpy(); lp = np.log(px)
print(f"ETH : {len(tk)} ticks | {len(win)} fenêtres | {len(tops)} tops")

# ── A. Nature du processus (rendements 1 s) ─────────────────────────────
dt = np.diff(ts)/1000.0; ret = np.diff(lp)
r1 = ret[(dt>=0.5)&(dt<=1.5)]; sd = r1.std()
prix_moy = px.mean()
print(f"\n== A. Processus ETH (prix moyen {prix_moy:.0f} $) ==")
print(f"sigma_1s={sd:.3e} ({sd*1e4:.2f} bp)  →  ~{sd*prix_moy:.3f} $/s  |  kurtosis excès={pd.Series(r1).kurt():.1f}")
for k in (3,5,8):
    obs=(np.abs(r1)>k*sd).mean(); theo=2*norm.sf(k)
    print(f"  P(|r|>{k}σ) obs {obs:.2e} vs gaussien {theo:.2e}  (×{obs/max(theo,1e-300):.0f})")

# ── B. Strike : tick pile à T0 ? ────────────────────────────────────────
gaps=[]
for w in win.itertuples():
    i=np.searchsorted(ts,w.t0_ms,"right")-1
    if i>=0 and ts[i]>=w.t0_ms-2000: gaps.append(w.t0_ms-ts[i])
gaps=np.array(gaps)
print(f"\n== B. Strike == {len(gaps)} fenêtres couvertes | gap=0 ms : {(gaps==0).mean()*100:.0f}%  | gap médian {np.median(gaps):.0f} ms")

# ── C. Simulation seconde par seconde (dist en $, ask du favori) ────────
# EWMA sigma le long des ticks
ew=np.full(len(ts),np.nan); v=np.nan
for i in range(1,len(ts)):
    d=(ts[i]-ts[i-1])/1000.0
    if d<=0.01: ew[i]=v; continue
    vi=ret[i-1]**2/d; lam=np.exp(-np.log(2)*d/HL)
    v=vi if np.isnan(v) else lam*v+(1-lam)*vi; ew[i]=v
sig=np.sqrt(ew)
# top-of-book par token
tops["a"]=tops.asset.astype(str)
# chaque token appartient à UNE fenêtre : map token -> (slug, side)
tok={}
for w in win.itertuples():
    tok[str(w.token_up)]=(w.slug,"up"); tok[str(w.token_down)]=(w.slug,"down")
tops["slug"]=tops.a.map(lambda x: tok.get(x,(None,None))[0])
tops["side"]=tops.a.map(lambda x: tok.get(x,(None,None))[1])
tops=tops.dropna(subset=["side"]).sort_values("recv_ms")

rows=[]
for w in win.itertuples():
    t0,te=w.t0_ms,w.end_ms
    i0=np.searchsorted(ts,t0,"right")-1; iF=np.searchsorted(ts,te,"right")-1
    if i0<0 or iF<=i0 or ts[i0]<t0-2000 or ts[iF]<te-2000: continue
    K=px[i0]; up_won = px[iF]>K
    for tsec in range(t0//1000+10, te//1000-2):
        tm=tsec*1000; i=np.searchsorted(ts,tm,"right")-1
        if ts[i]<tm-3000 or np.isnan(sig[i]) or sig[i]<=0: continue
        rows.append((w.slug, te-tm, px[i]-K, up_won, tm))
mom=pd.DataFrame(rows,columns=["slug","tau_ms","dist","up_won","tm"])
mom["tau"]=mom.tau_ms/1000.0; mom["fav_up"]=mom.dist>=0
mom["side_won"]=np.where(mom.fav_up,mom.up_won,~mom.up_won.astype(bool)).astype(bool)
# joindre l'ask du favori
def ask_join(side):
    t=tops[tops.side==side][["recv_ms","slug","ask"]]
    m=mom.reset_index()[["index","slug","tm"]]
    j=pd.merge_asof(m.sort_values("tm"),t.sort_values("recv_ms"),left_on="tm",right_on="recv_ms",by="slug",tolerance=6000,direction="backward")
    return j.set_index("index")["ask"].rename(f"ask_{side}")
mom=mom.join(ask_join("up")).join(ask_join("down"))
mom["ask_fav"]=np.where(mom.fav_up,mom.ask_up,mom.ask_down)
h=mom.dropna(subset=["ask_fav"]).copy()
NW=h.slug.nunique(); HEURES=NW*5/60
fee=lambda a:0.07*a*(1-a)
print(f"\n== C. Frontière ETH == {len(h)} états, {NW} fenêtres (~{HEURES:.1f} h)")

def wilson(k,n,z=1.28):
    if n==0: return 0.0
    p=k/n; d=1+z*z/n; c=p+z*z/(2*n); s=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n)); return (c-s)/d
def sim(dmin,tmax,cap,tmin=4):
    tr=[]
    for slug,g in h.groupby("slug"):
        g=g.sort_values("tau",ascending=False)
        c=g[(g.dist.abs()>=dmin)&(g.tau<=tmax)&(g.tau>=tmin)&(g.ask_fav<=cap)]
        if c.empty: continue
        e=c.iloc[0]; a=min(e.ask_fav+0.005,0.995)
        tr.append((bool(e.side_won), 250/a*(1-a)-250/a*fee(a) if e.side_won else -250-250/a*fee(a), a))
    if not tr: return None
    df=pd.DataFrame(tr,columns=["won","pnl","prix"]); n=len(df); k=int(df.won.sum())
    return dict(n=n,wr=k/n,plo=wilson(k,n),pnl=df.pnl.sum(),prix=df.prix.mean(),ph=n/HEURES)
print(f"{'écart$':>6} {'τmax':>5} {'prix≤':>6} │ {'n':>3} {'/h':>4} {'réuss':>6} {'P_lo90':>6} {'seuil':>6} {'PnL':>8}")
for dmin in (1,2,3,5,8):
    for tmax in (60,120):
        for cap in (0.94,0.98):
            r=sim(dmin,tmax,cap)
            if not r or r["n"]<5: continue
            seuil=r["prix"]+fee(r["prix"]); mk=" ◄" if r["plo"]>seuil else ""
            print(f"{dmin:>5}$ {tmax:>4}s {cap:>6.2f} │ {r['n']:>3} {r['ph']:>4.1f} {100*r['wr']:>5.1f}% {r['plo']:>6.3f} {seuil:>6.3f} {r['pnl']:>+8.1f}{mk}")
print("◄ = prouvé à 90 % (P_lo90 > prix+frais)")
