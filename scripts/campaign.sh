#!/usr/bin/env bash
# Boucle de campagnes paper : tranches de ~50 min, archivage après chaque
# tranche, arrêt quand TARGET_ENTRIES entrées taker sont atteintes (ou
# MAX_CYCLES tranches).
#
# Usage : scripts/campaign.sh [MAX_ENTRY] [TARGET_ENTRIES] [MAX_CYCLES] [SLICE_SECS] [MODE]
#   MODE = trade (défaut) : le taker prend des positions paper.
#   MODE = collecte        : --no-taker → AUCUN trade, PnL toujours nul ;
#                            la table de calibration apprend quand même
#                            (observation des fenêtres + règlements).
# Push git optionnel : n'a lieu que si PM_CAMPAIGN_PUSH=1 (désactivé par
# défaut — inutile sur un déploiement serveur où les données sont locales).
set -u
cd "$(dirname "$0")/.."
BASE="$(pwd)"
MAX_ENTRY="${1:-0.75}"
TARGET_ENTRIES="${2:-20}"
MAX_CYCLES="${3:-30}"
SLICE_SECS="${4:-3000}"
MODE="${5:-trade}"

if [ "$MODE" = "collecte" ]; then
  BOT_MODE_ARGS=(--no-taker)
  START_LABEL="COLLECTE (aucun trade, PnL nul) — apprentissage de la calibration"
else
  BOT_MODE_ARGS=(--max-entry "$MAX_ENTRY")
  START_LABEL="max_entry=$MAX_ENTRY cible=$TARGET_ENTRIES entrées"
fi

STATE="$BASE/data_v2/campaign_state.txt"
SUMMARY="$BASE/data_samples_campaign/campaign_summary.log"
mkdir -p "$BASE/data_v2/archives" "$BASE/data_samples_campaign"
total_entries=$(cat "$STATE" 2>/dev/null || echo 0)

echo "[campagne] démarrage: $START_LABEL, deja=$total_entries" | tee -a "$SUMMARY"

for cycle in $(seq 1 "$MAX_CYCLES"); do
  # En mode collecte, aucune entrée n'est prise : on ne s'arrête jamais sur
  # la cible (elle resterait à 0), uniquement au plafond de tranches.
  if [ "$MODE" != "collecte" ] && [ "$total_entries" -ge "$TARGET_ENTRIES" ]; then
    echo "[campagne] cible atteinte ($total_entries entrées) — arrêt" | tee -a "$SUMMARY"
    break
  fi
  ts=$(date -u +%Y%m%dT%H%M%S)
  RUN_DIR="$BASE/data_v2/camp_${ts}"
  mkdir -p "$RUN_DIR"
  echo "[campagne] cycle $cycle → $RUN_DIR (tranche ${SLICE_SECS}s)" | tee -a "$SUMMARY"
  CFG_ARGS=()
  [ -f "$BASE/config.toml" ] && CFG_ARGS=(--config "$BASE/config.toml")
  # Durée alignée sur une frontière de fenêtre 5 min + 40 s de grâce :
  # tuer le bot juste après un règlement, jamais avec une position ouverte
  # (leçon du 06/07 : trade du cycle 5 gagnant mais jamais comptabilisé).
  now_s=$(date +%s)
  end_s=$((now_s + SLICE_SECS))
  aligned=$(( ((end_s / 300) + 1) * 300 + 40 ))
  slice=$((aligned - now_s))
  RUST_LOG=info PM_CALIB_PATH="$BASE/data_v2/calibration.json" \
    timeout "$slice" "$BASE/target/release/pm-bot" \
    "${CFG_ARGS[@]}" --out "$RUN_DIR" "${BOT_MODE_ARGS[@]}" > "$RUN_DIR/run.log" 2>&1
  rc=$?

  entries=$(grep -ac "TAKER:" "$RUN_DIR/run.log" || true)
  confirms=$(grep -ac "CONFIRME" "$RUN_DIR/run.log" || true)
  contradictions=$(grep -ac "CONTREDIT" "$RUN_DIR/run.log" || true)
  pnl=$(grep -a "PnL cumulé" "$RUN_DIR/run.log" | tail -1 | sed 's/.*PnL cumulé=//' || echo "?")
  # En mode collecte, on ne touche pas au compteur d'entrées persistant.
  if [ "$MODE" != "collecte" ]; then
    total_entries=$((total_entries + entries))
    echo "$total_entries" > "$STATE"
  fi
  if [ "$MODE" = "collecte" ]; then
    fenetres=$(grep -ac "RÈGLEMENT" "$RUN_DIR/run.log" || true)
    echo "[collecte] cycle $cycle ($(basename "$RUN_DIR")) fini (rc=$rc): fenêtres=$fenetres confirmations=$confirms contradictions=$contradictions" | tee -a "$SUMMARY"
  else
    echo "[campagne] cycle $cycle ($(basename "$RUN_DIR")) fini (rc=$rc): entrées=$entries (cumul=$total_entries) pnl_tranche=$pnl confirmations=$confirms contradictions=$contradictions" | tee -a "$SUMMARY"
  fi

  # Archive complète (locale) + archive légère (poussée sur GitHub).
  name="camp_${ts}"
  for f in "$RUN_DIR"/journal_*.ndjson; do
    [ -e "$f" ] || continue
    seg=$(basename "$f" .ndjson)
    zstd -9 -T0 -q "$f" -o "$BASE/data_v2/archives/${name}_${seg}.ndjson.zst"
    python3 - "$f" "$BASE/data_samples_campaign/${name}_${seg}_light.ndjson" <<'PYEOF'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
keep_clob = ("last_trade_price", "market_resolved", "tick_size_change")
with open(src) as fi, open(dst, "w") as fo:
    for line in fi:
        try:
            fr = json.loads(line)
        except Exception:
            continue
        st = fr.get("stream")
        if st in ("rtds", "gamma") or (st == "clob" and any(k in fr.get("raw", "") for k in keep_clob)):
            fo.write(line)
PYEOF
    zstd -9 -T0 -q --rm "$BASE/data_samples_campaign/${name}_${seg}_light.ndjson"
    rm -f "$f"
  done
  cp "$RUN_DIR/run.log" "$BASE/data_samples_campaign/${name}_run.log"

  # Push git OPTIONNEL (désactivé par défaut) : n'a de sens que sur le dépôt
  # de développement. Sur un serveur, les données restent locales.
  if [ "${PM_CAMPAIGN_PUSH:-0}" = "1" ]; then
    cd "$BASE/.."
    git add polymarket-btc5m-bot/data_samples_campaign 2>/dev/null
    git commit -q -m "Campagne auto ${name}: cumul ${total_entries}" 2>/dev/null
    for wait in 2 4 8; do git push -q 2>/dev/null && break; sleep "$wait"; done
    cd "$BASE"
  fi
done
echo "[campagne] terminé: cumul=$total_entries entrées" | tee -a "$SUMMARY"
