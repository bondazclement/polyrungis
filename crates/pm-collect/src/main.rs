//! pm-collect — collecteur de données MULTI-ACTIFS pour les marchés
//! Polymarket « <asset> Up or Down 5m » (btc, eth, sol…).
//!
//! Enregistre TOUT verbatim (NDJSON v2, rejouable), sans aucune décision
//! de trading — c'est un outil d'observation pour l'analyse prospective :
//!   - ticks Chainlink de TOUS les symboles (dont eth/usd) via RTDS ;
//!   - spot Binance <symbol>@trade en direct (source lead-lag) ;
//!   - carnets CLOB up/down de chaque fenêtre (book, price_change,
//!     last_trade, market_resolved) ;
//!   - méta Gamma de chaque fenêtre.
//!
//! Réutilise l'acquisition du bot (rtds/clob/recorder) ; la découverte de
//! fenêtre est faite ici pour n'importe quel préfixe de slug.
//!
//! ```text
//! pm-collect --asset eth [--out DIR] [--duree-s N] [--lookahead N]
//! ```

use anyhow::{Context, Result};
use pm_acquisition::{clob, rtds, Bus, Recorder};
use std::time::Duration;
use tokio::time;

/// Descripteur d'un actif (tout ce qui change d'un marché à l'autre).
#[derive(Clone)]
struct Asset {
    /// Préfixe de slug Gamma, ex. "eth-updown-5m".
    slug_prefix: &'static str,
    /// Symbole Binance en minuscules, ex. "ethusdt".
    binance: &'static str,
    /// Symbole Chainlink (pour information ; RTDS enregistre tout).
    chainlink: &'static str,
}

fn asset(nom: &str) -> Option<Asset> {
    match nom {
        "btc" => Some(Asset { slug_prefix: "btc-updown-5m", binance: "btcusdt", chainlink: "btc/usd" }),
        "eth" => Some(Asset { slug_prefix: "eth-updown-5m", binance: "ethusdt", chainlink: "eth/usd" }),
        "sol" => Some(Asset { slug_prefix: "sol-updown-5m", binance: "solusdt", chainlink: "sol/usd" }),
        _ => None,
    }
}

struct Args {
    asset: String,
    out_dir: std::path::PathBuf,
    duree_s: u64,
    lookahead: u64,
}

fn parse_args() -> Result<Args> {
    let mut a = Args {
        asset: "eth".into(),
        out_dir: std::path::PathBuf::from("./data_collect"),
        duree_s: 0, // 0 = illimité (jusqu'à Ctrl-C)
        lookahead: 3,
    };
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--asset" => { i += 1; a.asset = argv[i].clone(); }
            "--out" => { i += 1; a.out_dir = argv[i].clone().into(); }
            "--duree-s" => { i += 1; a.duree_s = argv[i].parse()?; }
            "--lookahead" => { i += 1; a.lookahead = argv[i].parse()?; }
            "--help" | "-h" => {
                println!("pm-collect --asset {{btc|eth|sol}} [--out DIR] [--duree-s N] [--lookahead N]");
                std::process::exit(0);
            }
            other => anyhow::bail!("argument inconnu: {other}"),
        }
        i += 1;
    }
    Ok(a)
}

fn now_ms() -> u64 {
    pm_acquisition::now_ms()
}

/// Fenêtre découverte (minimal, indépendant du parseur BTC).
struct Fenetre {
    slug: String,
    start_ms: u64,
    end_ms: u64,
    token_up: String,
    token_down: String,
}

/// Découverte de la prochaine fenêtre ouverte pour un préfixe de slug.
async fn decouvrir(
    http: &reqwest::Client,
    prefix: &str,
    now_s: u64,
    lookahead: u64,
) -> Result<Option<Fenetre>> {
    let base = (now_s / 300) * 300;
    for k in 0..=lookahead {
        let epoch = base + k * 300;
        let slug = format!("{prefix}-{epoch}");
        let url = format!("https://gamma-api.polymarket.com/events?slug={slug}");
        let txt = http.get(&url).send().await?.text().await?;
        let v: serde_json::Value = serde_json::from_str(&txt).unwrap_or(serde_json::Value::Null);
        let Some(ev) = v.as_array().and_then(|a| a.first()) else { continue };
        let Some(m) = ev["markets"].as_array().and_then(|a| a.first()) else { continue };
        // clobTokenIds est une chaîne JSON : "[\"up\",\"down\"]".
        let ids: Vec<String> = m["clobTokenIds"]
            .as_str()
            .and_then(|s| serde_json::from_str(s).ok())
            .unwrap_or_default();
        if ids.len() < 2 {
            continue;
        }
        if m["closed"].as_bool().unwrap_or(false) {
            continue;
        }
        return Ok(Some(Fenetre {
            slug,
            start_ms: epoch * 1000,
            end_ms: (epoch + 300) * 1000,
            token_up: ids[0].clone(),
            token_down: ids[1].clone(),
        }));
    }
    Ok(None)
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();
    let args = parse_args()?;
    let asset = asset(&args.asset)
        .with_context(|| format!("actif inconnu: {} (btc|eth|sol)", args.asset))?;
    std::fs::create_dir_all(&args.out_dir)?;
    let recorder = Recorder::spawn(args.out_dir.clone());
    let bus = Bus::default(); // publié mais non consommé (collecte pure).

    tracing::info!(
        "pm-collect : actif={} slug={}-<epoch> chainlink={} binance={} → {}",
        args.asset, asset.slug_prefix, asset.chainlink, asset.binance, args.out_dir.display()
    );

    // Flux continus, indépendants des fenêtres :
    //  - RTDS enregistre TOUS les symboles Chainlink verbatim (dont le nôtre) ;
    //  - Binance direct pour le symbole de l'actif.
    tokio::spawn(rtds::run(bus.clone(), recorder.clone()));
    tokio::spawn(pm_acquisition::binance::run(recorder.clone(), asset.binance.to_string()));

    // Découverte + rotation des connexions CLOB (chevauchantes jusqu'à
    // résolution, comme le bot).
    let http = reqwest::Client::builder()
        .timeout(Duration::from_secs(8))
        .user_agent("pm-collect/0.1")
        .build()?;
    let debut = now_ms();
    let mut current = String::new();
    let mut tick = time::interval(Duration::from_secs(2));
    loop {
        tick.tick().await;
        if args.duree_s > 0 && now_ms().saturating_sub(debut) >= args.duree_s * 1000 {
            tracing::info!("durée atteinte ({} s) — arrêt de la collecte", args.duree_s);
            // Laisse le recorder flusher.
            time::sleep(Duration::from_millis(500)).await;
            return Ok(());
        }
        match decouvrir(&http, asset.slug_prefix, now_ms() / 1000, args.lookahead).await {
            Ok(Some(w)) if w.slug != current => {
                current = w.slug.clone();
                // Méta de la fenêtre (verbatim, stream "gamma").
                let meta = serde_json::json!({
                    "slug": w.slug, "start_ms": w.start_ms, "end_ms": w.end_ms,
                    "token_up": w.token_up, "token_down": w.token_down,
                });
                recorder.record("gamma", meta.to_string(), now_ms());
                tracing::info!("fenêtre {} [{} → {}]", w.slug, w.start_ms, w.end_ms);
                // Connexion CLOB dédiée, vivante jusqu'à résolution + 180 s.
                tokio::spawn(clob::run_for_tokens(
                    bus.clone(),
                    recorder.clone(),
                    w.token_up.clone(),
                    w.token_down.clone(),
                    w.end_ms + 180_000,
                ));
            }
            Ok(_) => {}
            Err(e) => tracing::warn!("découverte {}: {e:#}", asset.slug_prefix),
        }
    }
}
