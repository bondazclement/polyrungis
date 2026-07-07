#!/usr/bin/env bash
# micro-test.sh — micro-test RÉEL de A à Z, entièrement paramétrable.
#
#   ./scripts/micro-test.sh config              menu de paramétrage (persisté)
#   ./scripts/micro-test.sh lancer [--duree H]  demande la clé puis lance en fond
#   ./scripts/micro-test.sh arreter             arrêt propre (les positions se règlent)
#   ./scripts/micro-test.sh statut              raccourci pm-ctl statut
#   ./scripts/micro-test.sh params              affiche les paramètres effectifs
#
# Les paramètres (plafonds de risque, sizing, frontière, durée, compte) sont
# stockés dans config-micro-test.conf et réutilisés à chaque lancement — sur
# le serveur comme en local. La CLÉ PRIVÉE n'est JAMAIS stockée (demandée à
# chaque lancement, saisie masquée). Réclamation des gains : manuelle
# (Claim sur polymarket.com) — auto-redeem = chantier docs/VISION.md.
set -uo pipefail
BASE="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
PIDF="$BASE/data_v2/micro-test.pid"
CONF="$BASE/config-micro-test.conf"

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; C=$'\033[36m'; B=$'\033[1m'; D=$'\033[2m'; N=$'\033[0m'
else G=""; R=""; Y=""; C=""; B=""; D=""; N=""; fi

# ── Paramètres : défauts, puis surcharge par le fichier de conf ──────────
MT_MAX_ORDRE_USD=5.0        # plafond notional par ordre ($)
MT_MAX_ORDRES=20            # nombre max d'ordres par session
MT_PERTE_MAX_USD=20.0       # perte cumulée avant arrêt définitif ($)
MT_BANKROLL=23.0            # capital de référence pour le sizing (Kelly)
MT_DUREE_H=6               # durée par défaut (h)
MT_DIST_USD=70.0           # frontière : écart minimal spot↔strike ($)
MT_TAU_S=120.0             # frontière : temps restant maximal (s)
MT_PRIX_MAX=0.98           # frontière : prix d'achat maximal
MT_MARGE_EV=0.01           # frontière : marge d'EV nette exigée
MT_MODE_VALEUR=false       # mode « valeur » (déconseillé, mesuré −EV)
MT_FUNDER="0x8f770bAC16B72c2771322E412b377Bbf0Ad6844b"  # adresse (non secret)
MT_SIG_TYPE=1              # type de signature (0 EOA / 1 Proxy / 2 Safe / 3 Poly1271)
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"

sauver_conf() {
  cat > "$CONF" <<EOF
# Paramètres du micro-test réel — édités via ./scripts/micro-test.sh config
# (la clé privée n'est JAMAIS stockée ici.)
MT_MAX_ORDRE_USD=$MT_MAX_ORDRE_USD
MT_MAX_ORDRES=$MT_MAX_ORDRES
MT_PERTE_MAX_USD=$MT_PERTE_MAX_USD
MT_BANKROLL=$MT_BANKROLL
MT_DUREE_H=$MT_DUREE_H
MT_DIST_USD=$MT_DIST_USD
MT_TAU_S=$MT_TAU_S
MT_PRIX_MAX=$MT_PRIX_MAX
MT_MARGE_EV=$MT_MARGE_EV
MT_MODE_VALEUR=$MT_MODE_VALEUR
MT_FUNDER="$MT_FUNDER"
MT_SIG_TYPE=$MT_SIG_TYPE
EOF
  echo "${G}✔${N} Paramètres enregistrés dans config-micro-test.conf"
}

afficher_params() {
  echo "${B}══ PARAMÈTRES DU MICRO-TEST ══${N} ${D}($([ -f "$CONF" ] && echo "config-micro-test.conf" || echo "défauts"))${N}"
  echo " ${C}Garde-fous de risque${N}"
  printf "   %-34s %s\n" "1) Plafond par ordre" "${G}${MT_MAX_ORDRE_USD} \$${N}"
  printf "   %-34s %s\n" "2) Nombre max d'ordres / session" "${G}${MT_MAX_ORDRES}${N}"
  printf "   %-34s %s\n" "3) Perte max avant arrêt définitif" "${G}${MT_PERTE_MAX_USD} \$${N}"
  echo " ${C}Sizing${N}"
  printf "   %-34s %s\n" "4) Bankroll de référence" "${G}${MT_BANKROLL} \$${N}"
  echo " ${C}Stratégie — frontière${N}"
  printf "   %-34s %s\n" "5) Écart minimal spot↔strike" "${G}${MT_DIST_USD} \$${N}"
  printf "   %-34s %s\n" "6) Temps restant maximal" "${G}${MT_TAU_S} s${N}"
  printf "   %-34s %s\n" "7) Prix d'achat maximal" "${G}${MT_PRIX_MAX}${N}"
  printf "   %-34s %s\n" "8) Marge d'EV nette" "${G}${MT_MARGE_EV}${N}"
  printf "   %-34s %s\n" "9) Mode valeur (déconseillé)" "${G}${MT_MODE_VALEUR}${N}"
  echo " ${C}Session${N}"
  printf "   %-34s %s\n" "10) Durée par défaut" "${G}${MT_DUREE_H} h${N}"
  echo " ${C}Compte${N} ${D}(non secret ; la clé privée n'est jamais stockée)${N}"
  printf "   %-34s %s\n" "11) Adresse funder" "${G}${MT_FUNDER:0:10}…${MT_FUNDER: -4}${N}"
  printf "   %-34s %s\n" "12) Type de signature" "${G}${MT_SIG_TYPE}${N}"
}

# lit un nombre avec valeur courante par défaut, bornes optionnelles
lire_num() {
  local label="$1" cur="$2" min="${3:-}" max="${4:-}" v
  read -rp "   ${label} [${cur}] : " v
  [ -z "$v" ] && { echo "$cur"; return; }
  if ! [[ "$v" =~ ^[0-9]+([.][0-9]+)?$ ]]; then echo "$cur"; return; fi
  if [ -n "$min" ] && awk "BEGIN{exit !($v<$min)}"; then echo "$cur"; return; fi
  if [ -n "$max" ] && awk "BEGIN{exit !($v>$max)}"; then echo "$cur"; return; fi
  echo "$v"
}

menu_config() {
  while true; do
    clear 2>/dev/null || true
    afficher_params
    echo
    echo " ${Y}P${N}) Preset rapide   ${Y}S${N}) Sauvegarder & quitter   ${Y}Q${N}) Quitter sans sauver"
    read -rp "${B}Numéro à modifier ▸${N} " c
    case "$c" in
      1) MT_MAX_ORDRE_USD=$(lire_num "Plafond par ordre (\$)" "$MT_MAX_ORDRE_USD" 0.1 1000);;
      2) MT_MAX_ORDRES=$(lire_num "Nombre max d'ordres" "$MT_MAX_ORDRES" 1 10000);;
      3) MT_PERTE_MAX_USD=$(lire_num "Perte max (\$)" "$MT_PERTE_MAX_USD" 0.1 100000);;
      4) MT_BANKROLL=$(lire_num "Bankroll (\$)" "$MT_BANKROLL" 1 1000000);;
      5) MT_DIST_USD=$(lire_num "Écart minimal (\$)" "$MT_DIST_USD" 0 100000);;
      6) MT_TAU_S=$(lire_num "Temps restant max (s)" "$MT_TAU_S" 3 300);;
      7) MT_PRIX_MAX=$(lire_num "Prix max" "$MT_PRIX_MAX" 0.5 0.99);;
      8) MT_MARGE_EV=$(lire_num "Marge EV" "$MT_MARGE_EV" 0 0.5);;
      9) [ "$MT_MODE_VALEUR" = "true" ] && MT_MODE_VALEUR=false || MT_MODE_VALEUR=true;;
      10) MT_DUREE_H=$(lire_num "Durée (h)" "$MT_DUREE_H" 1 168);;
      11) read -rp "   Adresse funder [${MT_FUNDER}] : " v; [ -n "$v" ] && MT_FUNDER="$v";;
      12) MT_SIG_TYPE=$(lire_num "Type signature (0-3)" "$MT_SIG_TYPE" 0 3);;
      P|p)
        echo "   ${D}prudent (70/120/0,96) · standard (70/120/0,98) · agressif (40/120/0,98)${N}"
        read -rp "   Preset ▸ " p
        case "$p" in
          prudent)  MT_DIST_USD=70.0; MT_TAU_S=120.0; MT_PRIX_MAX=0.96; MT_MARGE_EV=0.015; MT_MODE_VALEUR=false;;
          standard) MT_DIST_USD=70.0; MT_TAU_S=120.0; MT_PRIX_MAX=0.98; MT_MARGE_EV=0.01;  MT_MODE_VALEUR=false;;
          agressif) MT_DIST_USD=40.0; MT_TAU_S=120.0; MT_PRIX_MAX=0.98; MT_MARGE_EV=0.005; MT_MODE_VALEUR=false;;
          *) echo "   ${R}preset inconnu${N}"; sleep 1;;
        esac;;
      S|s) sauver_conf; return 0;;
      Q|q) echo "${D}Aucune modification enregistrée.${N}"; return 0;;
      *) ;;
    esac
  done
}

# ─── Aiguillage des sous-commandes ───────────────────────────────────────
cas="${1:-lancer}"

case "$cas" in
  config)  menu_config; exit 0;;
  params)  afficher_params; exit 0;;
  arreter)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      kill -TERM "$(cat "$PIDF")" && sleep 2
      kill -0 "$(cat "$PIDF")" 2>/dev/null && kill -9 "$(cat "$PIDF")" || true
      rm -f "$PIDF"
      echo "${G}✔${N} Micro-test arrêté. Aucun nouvel ordre ne partira."
      echo "  Les positions déjà prises se règlent d'elles-mêmes à la résolution"
      echo "  des fenêtres (gains crédités sur votre compte Polymarket)."
    else
      pkill -TERM -f "[p]m-bot --live" 2>/dev/null && echo "${G}✔${N} Bot réel arrêté." || echo "▸ Aucun micro-test en cours."
      rm -f "$PIDF"
    fi
    exit 0;;
  statut)  exec "$BASE/scripts/pm-ctl" statut;;
  lancer)  ;;
  *) echo "usage : micro-test.sh {config|lancer|arreter|statut|params}"; exit 1;;
esac

# ── lancer ───────────────────────────────────────────────────────────────
set -e
DUREE_H="$MT_DUREE_H"
[ "${2:-}" = "--duree" ] && DUREE_H="${3:-$MT_DUREE_H}"

echo "${B}══ MICRO-TEST RÉEL ══${N}"
afficher_params
echo
echo "Durée de cette session : ${B}${DUREE_H} h${N} (arrêt auto aligné sur une fin de fenêtre)"
echo
pgrep -f "[p]m-bot" >/dev/null && { echo "${R}✘${N} Un bot tourne déjà (./scripts/micro-test.sh arreter d'abord)"; exit 1; }

# 1. Clé privée (jamais stockée) ; funder & type viennent de la conf.
if [ -z "${POLYMARKET_PRIVATE_KEY:-}" ]; then
  read -rsp "Clé privée du wallet (0x…, saisie masquée) : " POLYMARKET_PRIVATE_KEY; echo
  export POLYMARKET_PRIVATE_KEY
fi
export POLYMARKET_FUNDER="$MT_FUNDER"
export POLYMARKET_SIG_TYPE="$MT_SIG_TYPE"

# 2. Binaire live à jour.
BIN="$BASE/target/release/pm-bot"
echo "▸ Compilation (--features live)…"
(cd "$BASE" && cargo build --release --features live -p pm-bot -q)

# 3. Config effective du test (générée depuis les paramètres persistés).
cat > "$BASE/config-micro.toml" <<EOF
# Micro-test réel — généré par scripts/micro-test.sh depuis config-micro-test.conf
[taker]
mode_valeur = $MT_MODE_VALEUR
dist_frontiere_usd = $MT_DIST_USD
tau_frontiere_s = $MT_TAU_S
prix_max_frontiere = $MT_PRIX_MAX
marge_ev = $MT_MARGE_EV
bankroll = $MT_BANKROLL
max_notional = $MT_MAX_ORDRE_USD
kelly_fraction = 1.0
EOF

# 4. Lancement (fond + PID + arrêt auto aligné fenêtre).
ts=$(date -u +%Y%m%dT%H%M%S)
OUT="$BASE/data_v2/run_live_${ts}"
mkdir -p "$OUT"
now_s=$(date +%s); fin=$(( ( (now_s + DUREE_H*3600) / 300 + 1) * 300 + 40 - now_s ))
export PM_LIVE_ARME=oui PM_CALIB_PATH="$BASE/data_v2/calibration.json"
# marge de +0,2 $ sur le plafond du RiskGate (le prix limite = avg + slippage).
export PM_MAX_ORDRE_USD="$(awk "BEGIN{print $MT_MAX_ORDRE_USD + 0.2}")"
export PM_MAX_ORDRES="$MT_MAX_ORDRES" PM_PERTE_MAX_USD="$MT_PERTE_MAX_USD"
RUST_LOG=info nohup timeout "$fin" "$BIN" --live \
  --config "$BASE/config-micro.toml" --out "$OUT" > "$OUT/run.log" 2>&1 &
echo $! > "$PIDF"
disown
sleep 6
if grep -aq "MODE RÉEL ARMÉ" "$OUT/run.log"; then
  grep -a "MODE RÉEL ARMÉ" "$OUT/run.log" | sed 's/\x1b\[[0-9;]*m//g;s/.*WARN pm_bot: /✔ /'
  echo "${G}✔${N} Micro-test lancé (pid $(cat "$PIDF"), arrêt auto dans ~${DUREE_H} h)"
  echo "  Suivi : pm-ctl statut · pm-ctl suivre · http://localhost:7777 (chip RÉEL ARMÉ)"
  echo "  Arrêt : ./scripts/micro-test.sh arreter"
else
  echo "${R}✘${N} Démarrage réel refusé — dernières lignes :"
  tail -5 "$OUT/run.log" | sed 's/\x1b\[[0-9;]*m//g'
  rm -f "$PIDF"
  exit 1
fi
