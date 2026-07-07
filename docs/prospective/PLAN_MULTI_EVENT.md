# Plan prospectif — porter le bot à d'autres events Polymarket (ETH d'abord)

Branche : `prospective/multi-event` (le MVP BTC sur `main` reste intact).
Objectif : réutiliser l'acquis (frontière, calibration, exécution, risque)
pour d'autres marchés « <asset> Up or Down 5m » de Polymarket, en
commençant par **ETH** (`eth-updown-5m-<epoch>`).

---

## Constats de reconnaissance (sondes réelles + doc Polymarket)

1. **Structure identique à BTC.** Sonde Gamma : `eth-updown-5m-<epoch>`,
   outcomes `[Up, Down]`, mêmes `clobTokenIds` / `conditionId`, fenêtres
   de 5 min. → l'acquisition se généralise en changeant le **symbole**
   et le **préfixe de slug**.
2. **Flux Chainlink ETH confirmé.** Sonde RTDS : le topic
   `crypto_prices_chainlink` diffuse `eth/usd` (1777 $, cadence 1/s,
   full_accuracy 18 décimales) aux côtés de btc, sol, bnb, doge, hype.
   Résolution ETH = Chainlink ETH/USD data stream (règle fournie).
3. **⚠️ Délai taker de 250 ms (découverte doc).** *« Selected crypto and
   finance up/down markets apply a 250 ms taker delay to marketable
   orders »* (`itode: true`). **C'est l'explication des échecs FAK du
   micro-test BTC** en fin de fenêtre : le prix bouge pendant le hold.
   Contrainte d'exécution de PREMIÈRE classe pour tout bot de cette
   famille — et un argument fort pour privilégier les entrées avec plus
   de temps/de profondeur.
4. **Endpoint `prices-history`** (`/prices-history?market=TOKEN&startTs&endTs`)
   : historique de prix par token sur fenêtres passées → permet d'amorcer
   l'analyse ETH sans tout attendre en live.
5. **ETH ≠ BTC en dynamique.** ETH est structurellement plus volatil en %
   → les écarts-dollars de la « frontière » BTC (≥ 70 $) ne se
   transposent PAS tels quels. **La calibration doit être par actif**
   (une table écart$×τ propre à ETH). C'est l'hypothèse centrale à tester.

---

## MACRO — la vision (multi-actifs, config-driven)

Polymarket opère la même mécanique sur plusieurs actifs (btc, eth, sol,
bnb, xrp, doge…). L'objectif long terme : **un moteur unique paramétré par
un descripteur d'actif** (symbole Chainlink, préfixe de slug, symbole
Binance, échelle de prix, table de calibration dédiée). Chaque actif est
une instance ; le code de décision, d'exécution et de risque est partagé.

Jalons macro :
- **M1 — Généralisation de l'acquisition** (ce chantier) : collecter
  n'importe quel actif verbatim.
- **M2 — Généralisation du modèle** : `AssetConfig` + table de calibration
  par actif ; le taker « frontière » lit les paramètres de l'actif.
- **M3 — Multi-instances** : un orchestrateur qui fait tourner N actifs en
  parallèle, chacun avec sa calibration et ses garde-fous, capital partagé.
- **M4 — Exécution consciente du délai 250 ms** : sizing/limit adaptés au
  hold (viser les états à liquidité stable, éviter les 30 dernières s).

## MESO — qualifier ETH spécifiquement

Répliquer, sur ETH, la démarche qui a produit le modèle BTC — mais SANS
présumer que les mêmes chiffres tiennent :
1. **Exactitude du strike** : le dernier tick `eth/usd` ≤ T0 reconstruit-il
   le « price to beat » affiché (5/5 comme BTC) ?
2. **Nature du processus** : kurtosis, queues, autocorrélation des
   rendements ETH 1 s (probablement queues encore plus épaisses).
3. **Existe-t-il une frontière ETH ?** Balayage écart$×τ×prix comme
   l'étude 6 BTC, avec bornes de Wilson. L'écart-seuil sera différent
   (ETH ~1800 $ vs BTC ~63 000 $ : mêmes % → écarts-dollars ~35× plus
   petits ; mais volatilité % supérieure).
4. **Microstructure & délai** : profondeur du carnet ETH, overround,
   impact du hold 250 ms sur l'exécutabilité (rejouer les FAK).

## MICRO — les livrables concrets, dans l'ordre

1. **[CE CHANTIER] Module de collecte `pm-collect`** (A→Z) : découverte
   des fenêtres ETH, enregistrement verbatim de TOUT — ticks Chainlink
   (tous symboles, dont eth/usd), spot Binance ethusdt direct, carnets
   CLOB up/down (book + price_change + last_trade + market_resolved),
   méta Gamma. Sortie NDJSON v2 rejouable. Paramétré par actif (réutilise
   rtds/clob/recorder ; Binance généralisé au symbole).
2. **[APRÈS VOTRE FEU VERT] Collecte live 5-6 h** sur ETH + backfill
   `prices-history` sur les fenêtres récentes.
3. **Analyse quantitative** (scripts `analysis/eth/`) : extracteur ETH,
   étude strike, étude processus, table de calibration écart$×τ ETH,
   frontière d'efficience ETH, faisabilité d'exécution sous délai 250 ms.
4. **Verdict de faisabilité** : y a-t-il un edge ETH ? à quels
   paramètres ? Décision go/no-go pour un bot ETH, documentée comme
   `DECISIONS.md` (preuves chiffrées, y compris les impasses).

## Principe directeur (rappel méthodologique)

Comme pour BTC : **les données priment sur l'intuition et sur le prompt.**
On ne suppose pas que « ce qui marche sur BTC marche sur ETH » — on le
mesure. Chaque chiffre transposé doit être re-vérifié sur les données ETH
avant d'être codé.
