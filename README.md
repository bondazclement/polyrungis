```
 ____    ___   _     __   __ ____   _   _  _   _   ____  ___  ____
|  _ \  / _ \ | |    \ \ / /|  _ \ | | | || \ | | / ___||_ _|/ ___|
| |_) || | | || |     \ V / | |_) || | | ||  \| || |  _  | | \___ \
|  __/ | |_| || |___   | |  |  _ < | |_| || |\  || |_| | | |  ___) |
|_|     \___/ |_____|  |_|  |_| \_\ \___/ |_| \_| \____||___||____/
            \|/   le poireau qui trade · du frais, du local, du BTC
            /|\
```

# 🥬 polyrungis — Bot Polymarket BTC Up/Down 5 minutes

Bot de trading autonome pour le marché **« Bitcoin Up or Down »** de
Polymarket (`btc-updown-5m-<epoch>`) : toutes les 5 minutes, le marché
résout selon que le prix Chainlink BTC/USD a monté ou baissé depuis un
« price to beat ». Le bot reconstruit ce strike, mesure la volatilité,
estime la probabilité de résolution et n'entre que dans une zone
statistiquement prouvée gagnante.

> **polyrungis poireaute jusqu'à la frontière** — il n'entre que
> dans la zone prouvée gagnante, et attend patiemment le reste du temps.

*polyrungis* (clin d'œil au marché de Rungis, et à *poireauter* = attendre)
est écrit en **Rust**
(workspace multi-crates), 95 tests, paper trading et
exécution réelle sous garde-fous, interface web locale, installateur
multilingue.

---

## ✨ En un coup d'œil

| | |
|---|---|
| 🎯 **Modèle** | « la frontière » — entrée si écart au strike ≥ 70 $ **et** ≤ 120 s restantes **et** prix ≤ 0,98 **et** EV calibrée positive |
| 🧠 **Calibration** | table auto-apprise (écart-dollars × temps restant), mise à jour à chaque fenêtre réglée, persistée |
| 📡 **Source unique** | flux Chainlink natif de Polymarket (RTDS) — aucune source externe pour la résolution |
| 🛡️ **Sûreté** | paper par défaut ; mode réel = triple opt-in + plafonds durs + kill-switch automatique |
| 🖥️ **Interface** | dashboard web local (bougies, carnets, volatilité, calibration, config) |
| ⚡ **Performance** | ~20 Mo RAM, ~2 % d'un cœur ; décision événementielle à chaque tick |

## 🚀 Démarrage rapide

```bash
git clone https://github.com/bondazclement/polyrungis.git
cd polyrungis
./install.sh                 # installateur interactif (FR/EN/DE)
```

L'installateur détecte votre distribution (Fedora · Ubuntu · Debian ·
Arch · openSUSE), installe les dépendances, compile, lance les tests, et
ouvre une console de navigation vers toutes les étapes (vérification,
diagnostic, configuration, dry run, test d'ordres, micro-test, dashboard).

Installation directe non interactive (serveur/CI) : `./install.sh --auto`.

## 🎛️ Utilisation

```bash
pm-ctl sante          # connectivité Polymarket
pm-ctl demarrer       # dry run (paper trading, aucun ordre réel)
pm-ctl statut         # supervision : fenêtre, strike, flux, PnL
pm-ctl rapport        # règlements + entrées
pm-ctl arreter        # arrêt propre
```

Tableau de bord web : lancez `pm-dash` (ou l'option 8 de l'installateur)
puis ouvrez **http://localhost:7777**.

## 🧩 Architecture

Workspace Cargo de 7 crates — chaque décision est une fonction pure
rejouable au tick près, donc le **backtest utilise exactement le code du
live**.

| Crate | Rôle |
|---|---|
| `pm-core` | types, parsing, carnet L2, strike, volatilité (EWMA), maths (Student-t) |
| `pm-acquisition` | WebSockets RTDS / CLOB / Gamma / Binance, enregistrement verbatim, watchdog |
| `pm-strategy` | modèle probabiliste, table de calibration, taker « frontière », config |
| `pm-execution` | passerelle paper / réelle (SDK officiel) + garde-fous de risque |
| `pm-bot` | orchestrateur événementiel |
| `pm-replay` | backtest fidèle au live (walk-forward, score de Brier) |
| `pm-dash` | interface web locale (lecture seule) |

Détail : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 🛡️ Sûreté de l'exécution réelle

Le mode réel n'est atteignable qu'avec **trois verrous simultanés** :
compilation `--features live`, drapeau `--live`, variable
`PM_LIVE_ARME=oui`. Il est alors encadré par une couche de risque
(`RiskGate`) : plafond de notional par ordre, nombre d'ordres maximal,
**perte maximale de session (arrêt définitif)**, et **kill-switch
automatique** sur toute contradiction entre l'issue estimée et la
résolution officielle. Tout refus est journalisé.

Le paper trading, lui, ne peut structurellement passer aucun ordre : la
passerelle réelle n'est même pas compilée par défaut.

## 📚 Documentation

Point d'entrée : [`docs/README.md`](docs/README.md) (index par usage).

- **Comprendre** : [`docs/HISTORIQUE.md`](docs/HISTORIQUE.md) ·
  [`docs/DECISIONS.md`](docs/DECISIONS.md) ·
  [`docs/MODELE_V3.md`](docs/MODELE_V3.md) ·
  [`docs/VISION.md`](docs/VISION.md)
- **Les études** (preuves chiffrées) :
  [`docs/ETUDE_MODELE.md`](docs/ETUDE_MODELE.md) ·
  [`docs/LIGNE_EFFICIENCE.md`](docs/LIGNE_EFFICIENCE.md) ·
  [`docs/AUDIT_VITESSE.md`](docs/AUDIT_VITESSE.md)
- **Exploiter** : [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) ·
  [`docs/CREDENTIALS.md`](docs/CREDENTIALS.md) ·
  [`docs/MVP_REEL.md`](docs/MVP_REEL.md)
- **Déployer** : [`docs/DEPLOIEMENT_UPCLOUD.md`](docs/DEPLOIEMENT_UPCLOUD.md)
- **Identité** : [`docs/IDENTITE.md`](docs/IDENTITE.md) 🥬 (logo, mascotte, palette, devises)

## ⚠️ Avertissement

Logiciel expérimental de recherche. Le trading de contrats sur événements
comporte un risque de perte totale du capital engagé. Les résultats de
backtest ne garantissent pas les performances futures. La disponibilité de
Polymarket est soumise à des restrictions réglementaires selon les
juridictions — assurez-vous de votre conformité. Aucune garantie ; usage
à vos propres risques.

## 📄 Licence

**Apache License 2.0** — voir [`LICENSE`](LICENSE) et [`NOTICE`](NOTICE).
Usage, modification et redistribution libres, à condition de conserver
l'attribution, de signaler les modifications, et sans usage du nom de
l'auteur pour endosser des dérivés. Fourni sans aucune garantie.

Copyright 2026 Clément Bondaz.
