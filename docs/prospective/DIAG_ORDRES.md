# Diagnostic du passage d'ordre taker — pourquoi le bot n'entre pas

Analyse des ordres réels du micro-test du 06-07/07 (run_live_20260706T232310,
6 h, 813 Mo de carnet brut). Script : `analysis/diag_ordres.py`.

## Le symptôme (observation utilisateur)

Pendant un run, le bot n'entre que sur 2 positions alors qu'il y a ~5
moments favorables dans la fenêtre. Entrées manuelles aux 5 moments :
5/5 gagnantes. Les ordres du bot « ne sont pas comptés » par Polymarket.

## Ce que disent les données

8 décisions taker : **4 exécutées (τ = 101, 112, 114, 117 s), 4 échouées
(τ = 46, 47, 48 s)**. Séparation nette : les échecs sont tous en **fin de
fenêtre**, les succès tous à **τ > 100 s**.

Erreur des échecs : `no orders found to match with FAK order`.

### La cause n'est PAS le délai de 250 ms — c'est un CARNET PÉRIMÉ

Sur l'ordre échoué de 01:59:12 (DOWN) :
- le bot décide sur **ask = 0,970** → envoie une limite à 0,980 ;
- mais le carnet **réellement enregistré** à cet instant était
  **ask = 0,990 / bid = 0,980, stable depuis plusieurs secondes**.

Le bot a donc agi sur une **liquidité fantôme** (0,970) qui n'existait
plus. Sa limite 0,980 était sous le vrai ask 0,990 → aucun appariement.

**Pourquoi le carnet du bot est faux ?** Instabilité des connexions CLOB :
- **90 reconnexions CLOB et 16 resets** (« Connection reset without closing
  handshake ») sur 6 h — une coupure toutes les ~4 min ;
- un reset à **01:57:55**, 75 s avant l'échec ;
- après un reset, la reconstruction du carnet (snapshot + deltas) diverge
  du marché : des `price_change` sont perdus pendant le trou, et le bot
  garde des niveaux périmés.

Le FAK qui échoue est en réalité un **garde-fou** : il a empêché d'acheter
au mauvais prix. Mais le vrai défaut est en amont — **le bot a décidé sur
un carnet faux**.

### Détail complémentaire : la marge d'EV en fin de fenêtre

Même avec un carnet FRAIS (vrai ask 0,990), la marge d'EV actuelle (0,01)
rejetterait 0,990 comme trop cher pour p ≈ 0,994. Or les entrées manuelles
à ~0,99 étaient gagnantes → soit la vraie probabilité aux grands écarts /
τ courts est supérieure à ce que la table estime (bacs peu peuplés), soit
la marge est trop conservatrice pour ces états à p très élevé.

## Recommandations pour 1.0 Aligre (par ordre d'impact)

1. **Intégrité du carnet (le correctif racine).**
   - Après une reconnexion CLOB, marquer le carnet « non fiable » jusqu'à
     réception d'un `book` snapshot complet ; **ne pas trader** tant que le
     carnet n'est pas re-synchronisé (comme le garde-fou de confiance du
     strike).
   - Détecter un carnet figé (aucun update depuis N ms en fin de fenêtre) →
     pas d'entrée.
   - Horodater chaque niveau ; refuser de décider sur un carnet dont le
     dernier update dépasse un seuil de fraîcheur.

2. **Stabilité des connexions CLOB.** 90 reconnexions/6 h est anormal.
   Piste : le modèle à connexions chevauchantes ouvre trop de sockets
   (rate-limit 429 observé), les resets serveur ne sont pas amortis.
   → une seule connexion multiplexée par fenêtre, backoff plus doux,
   ping/pong applicatif, et surtout **re-souscription plus rapide** quand
   le flux devient muet (objectif utilisateur : rappel < 1000-1500 ms).

3. **Re-validation au moment de l'envoi.** Juste avant d'émettre le FAK,
   relire le meilleur ask le plus frais ; recalculer l'EV au prix réel ;
   envoyer seulement si l'EV reste positive. Fixer la limite = prix
   d'EV-équilibre (p_calibrée − frais − marge), pas ask + 1 centime.

4. **Calibration aux extrêmes.** Les bacs « grand écart × τ court » sont
   peu peuplés → p sous-estimée. La collecte continue (BTC + 6 h ETH) les
   remplit. Réévaluer la marge d'entrée en fin de fenêtre une fois ces
   bacs robustes.

5. **Type d'ordre (à tester).** Un ordre GTC qui repose sur le carnet est
   « compté » par Polymarket et peut se remplir sur une oscillation, là où
   le FAK est tué. À comparer au FAK sur données, sans dégrader l'EV.

## Verdict (recadré — précision utilisateur du 07/07)

Le sujet de fond n'est ni le délai de 250 ms, ni la vitesse de décision du
bot, ni même l'instabilité des connexions (aggravateur secondaire) : c'est
une **ASYMÉTRIE DE LATENCE STRUCTURELLE**. Les WebSocket CLOB/RTDS se
rafraîchissent en moyenne toutes les **~600-1500 ms** ; entre deux mises à
jour, le marché réel bouge alors que le carnet du bot ne bouge pas. Le
carnet et les données sont donc **en permanence un peu faux** — un léger
retard constant, invisible quand le marché est calme, décisif quand il
court (fin de fenêtre, gros écart).

Conséquence : le bot décide toujours sur un état légèrement passé. Ce n'est
pas réparable par un « meilleur ordre » ; c'est une propriété du canal de
données. Les leviers réels :
- **mesurer précisément cette asymétrie** (cadence de rafraîchissement par
  flux, distribution du retard) → fait en addendum sur les données ETH ;
- **modéliser le retard** : décider en tenant compte du fait que le carnet
  vu a un âge moyen connu (extrapoler, ou élargir les marges en fonction de
  l'âge du dernier update) ;
- **re-souscription/rappel plus rapide** quand un flux ralentit (cible
  utilisateur < 1000-1500 ms) pour réduire l'amplitude de l'asymétrie ;
- ne trader que quand la fraîcheur du carnet est suffisante (garde-fou).

Ce sera étudié quantitativement **après le modèle ETH** (ordre du plan
initial), en addendum à l'analyse de la collecte ETH.
