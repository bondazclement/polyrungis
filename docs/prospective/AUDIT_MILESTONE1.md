# Audit sévère du milestone 1 (modèle ETH + diagnostic ordres) — 07/07

Demandé par l'utilisateur avant d'engager la refonte : vérifier que les
analyses et solutions proposées étaient les plus optimisées, corriger et
approfondir. Six contrôles menés.

## ✅ Contrôles qui RENFORCENT les conclusions

**1. Biais de régime (l'échantillon 6 h est-il une tendance unique ?)**
Non : les heures alternent (−12,8 / −10,1 / +19,4 / +7,6 / +7,8 / +3,7 $)
— baisse ET hausse dans l'échantillon. Split moitié/moitié : 100 % vs
94,7 % de leaders confirmés. La frontière tient dans les deux régimes.

**2. Anomalie vs diffusion (96 % mesuré là où la diffusion prédit ~70 % ?)**
Fausse alerte de l'auditeur : l'écart médian des entrées réelles est
2,56 $ (pas 1 $) → z ≈ 1,37 → la diffusion prédit 91 %, mesuré 97 %.
L'écart restant (+6 pts) est cohérent avec les queues épaisses. Pas
d'anomalie structurelle.

**3. Réalisme d'exécution (le PnL simulé survit-il aux fills réels ?)**
Re-simulation avec ask FRAIS (≤ 1,5 s) + FILL-CHECK (l'ask à +600 ms —
délai taker 250 ms + latence — doit encore être ≤ limite, sinon FAK tué) :
- écart ≥ 1 $ : +1 831 → **+1 717 $** (−6 %), toujours prouvé ◄
- écart ≥ 2 $ : +918 → **+923 $** (stable), toujours prouvé ◄
La frontière ETH survit au réalisme d'exécution. (Les fills parfaits ne
sont PAS l'hypothèse porteuse du résultat.)

## 🔴 Correctif appliqué

**4. Règle de résolution `>` vs `>=`.** La règle officielle (fournie pour
ETH, même famille pour BTC) dit « greater than **or equal** » ; le moteur
estimait Up avec `t.price > k` strictement. Aucune égalité parfaite
observée sur 240 fenêtres (0 impact à ce jour, prix à 18 décimales) mais
bug latent → corrigé en `>=` (moteur, backtest, étude). 95 tests verts.

## 🟡 Amélioration MAJEURE trouvée (ratée dans ma première analyse)

**5. Le canal `best_bid_ask` dormant.** Nos journaux contiennent
**221 387 événements `best_bid_ask`** (souscription custom_feature déjà
active) : top-of-book AUTORITAIRE, horodaté serveur, avec spread. Le
parseur le décode déjà (`ClobEvent::BestBidAsk` dans pm-core::parse)…
mais le moteur le JETTE (`_ => {}` dans on_clob).

C'est la solution la plus optimisée au problème d'asymétrie de latence —
meilleure que mes propositions initiales (extrapolation par l'oracle) :
- source directe du meilleur bid/ask, sans reconstruction snapshot+deltas
  (la source des « prix fantômes » du micro-test) ;
- timestamp serveur par événement → l'ÂGE du top-of-book devient mesurable
  précisément → garde-fou de fraîcheur exact ;
- déjà reçu, déjà parsé : le coût d'intégration est minime.

**Décision pour 1.0 Aligre : le moteur consommera BestBidAsk comme source
primaire du top-of-book (décisions + re-validation à l'envoi), le carnet
reconstruit ne servant plus qu'à la profondeur (sizing).**

**6. Cadence réelle des prix (recadrage validé).** 1 vrai changement de
best_ask pour 103 messages ; intervalle médian 230 ms, p90 1 590 ms —
l'observation utilisateur (600-1500 ms) correspond à la queue de la
distribution, qui est exactement là où les décisions de fin de fenêtre se
jouent.

## Verdict d'audit

Les conclusions du milestone 1 tiennent (frontière ETH réelle, robuste au
régime et au réalisme d'exécution). Deux corrections en sortent : la règle
`>=` (appliquée) et surtout la refonte du chemin de décision autour de
`best_bid_ask` (à faire dans 1.0 Aligre) — qui remplace avantageusement
une partie des solutions proposées initialement.
