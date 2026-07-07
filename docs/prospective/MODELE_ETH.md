# Modèle ETH — qualification sur 6 h de collecte (07/07/2026)

Données : `pm-collect --asset eth`, 6,0 h, 73 fenêtres, 18 716 ticks
eth/usd (haute précision full_accuracy). Scripts : `analysis/eth/`.

## A. Nature du processus ETH

- Prix moyen 1 786 $ ; **σ_1s ≈ 0,96 bp ≈ 0,17 $/s**.
- **Kurtosis excédentaire = 9,8** — bien plus faible que BTC (238) : queues
  épaisses mais moins extrêmes. P(|r|>5σ) reste ×4 500 le taux gaussien.
- Conséquence : processus plus « lisse » que BTC → frontière plus nette.

## B. Strike (price to beat)

- Reconstruction = dernier tick eth/usd ≤ T0 (même politique que BTC).
- **97 % des fenêtres ont un tick pile à T0 (gap 0 ms)**, médiane 0 ms.
- Vérifié contre l'affichage Polymarket : **4/4 exacts au centime** (avec
  plus de précision que l'UI). Cf. échange du 07/07.

## C. La frontière ETH (le résultat central)

Balayage écart-$ × τ × prix, borne de Wilson 90 %, 62 fenêtres (~5,2 h) :

| écart ≥ | τ ≤ | prix ≤ | trades | /h | réussite | P_lo90 vs seuil | PnL simulé |
|---|---|---|---|---|---|---|---|
| **1 $** | 120 s | 0,98 | 54 | **10,5** | 96,3 % | 0,914 > 0,858 ✅ | +1 831 $ |
| **2 $** | 120 s | 0,98 | 34 | **6,6** | 100 % | 0,954 > 0,908 ✅ | +918 $ |
| 3 $ | 120 s | 0,98 | 23 | 4,5 | 100 % | 0,934 < 0,952 | +299 $ |
| 1-2 $ | 60 s | — | — | 2-8 | 91-100 % | mixte | + |

La zone **écart ≥ 1-2 $ / τ ≤ 120 s** est prouvée à 90 %, très fréquente,
à haut taux de réussite. Le seuil d'écart (~1-2 $) est ~35× plus petit que
BTC (~70 $), cohérent avec l'échelle de prix — invisible sans la précision
au sous-centime.

## D. ETH vs BTC — la thèse des deux marchés en parallèle

| | BTC | ETH |
|---|---|---|
| Frontière prouvée | écart ≥ 70 $, τ ≤ 120 s | écart ≥ 1-2 $, τ ≤ 120 s |
| Fréquence | ~2,6 trades/h | **6,6-10,5 trades/h** |
| Réussite | 100 % (34/34) | 96-100 % |
| Kurtosis | 238 | 9,8 |

**ETH seul offre 3-4× plus d'opportunités que BTC.** Les deux en parallèle
→ potentiellement ~10-13 trades/h combinés. La thèse « deux univers de
trade pour des entrées plus régulières » est solidement soutenue par les
données.

## Réserves d'honnêteté (impératif méthodologique)

1. **PnL simulé = borne HAUTE** : il suppose des fills parfaits. Le
   diagnostic d'ordres (DIAG_ORDRES.md) montre qu'en réel, l'asymétrie de
   latence fait rater des entrées valides. Le PnL réel sera inférieur —
   c'est précisément ce que le dry run ETH et l'addendum latence
   mesureront.
2. **In-sample, 6 h d'un seul jour** : pas de hold-out ; les bacs serrés
   (2-3 $) reposent sur 23-34 trades. À confirmer sur plus de données et
   hors échantillon.
3. **Même risque de sélection** qu'en BTC (balayage de variantes) — mais la
   région entière ≥ 1-2 $ est cohérente, pas une cellule chanceuse isolée.

## Verdict

Feu vert technique pour la suite : ETH est un candidat solide, plus
fréquent que BTC. Prochaines étapes du plan : (2) dry run ETH 1 h +
addendum asymétrie de latence, (3) refonte moteur dual 1.0 Aligre.
