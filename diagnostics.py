"""Rich diagnostic runner: run 100 sims in batches and report detailed stats."""
import sys
import numpy as np
import amm_sim_rs
from amm_competition.evm.compiler import SolidityCompiler
from amm_competition.evm.adapter import EVMStrategyAdapter
from amm_competition.evm.baseline import load_vanilla_strategy
from amm_competition.competition.config import (
    BASELINE_SETTINGS, BASELINE_VARIANCE, resolve_n_workers,
)

TOTAL_SIMS = 100
BATCH_SIZE = 25

def build_configs(start_seed, count):
    variance = BASELINE_VARIANCE
    configs = []
    for i in range(start_seed, start_seed + count):
        rng = np.random.default_rng(seed=i)
        retail_mean_size = rng.uniform(variance.retail_mean_size_min, variance.retail_mean_size_max)
        retail_arrival_rate = rng.uniform(variance.retail_arrival_rate_min, variance.retail_arrival_rate_max)
        gbm_sigma = rng.uniform(variance.gbm_sigma_min, variance.gbm_sigma_max)
        cfg = amm_sim_rs.SimulationConfig(
            n_steps=BASELINE_SETTINGS.n_steps,
            initial_price=BASELINE_SETTINGS.initial_price,
            initial_x=BASELINE_SETTINGS.initial_x,
            initial_y=BASELINE_SETTINGS.initial_y,
            gbm_mu=BASELINE_SETTINGS.gbm_mu,
            gbm_sigma=gbm_sigma,
            gbm_dt=BASELINE_SETTINGS.gbm_dt,
            retail_arrival_rate=retail_arrival_rate,
            retail_mean_size=retail_mean_size,
            retail_size_sigma=BASELINE_SETTINGS.retail_size_sigma,
            retail_buy_prob=BASELINE_SETTINGS.retail_buy_prob,
            seed=i,
        )
        configs.append(cfg)
    return configs

def run_diagnostics(sol_path, label=None):
    source_code = open(sol_path).read()
    compiler = SolidityCompiler()
    compilation = compiler.compile(source_code)
    if not compilation.success:
        print(f"Compile failed: {compilation.errors}")
        return None
    user = EVMStrategyAdapter(bytecode=compilation.bytecode, abi=compilation.abi)
    name = label or user.get_name()
    baseline = load_vanilla_strategy()
    n_workers = resolve_n_workers()

    # Collect per-sim data
    all_results = []
    for batch_start in range(0, TOTAL_SIMS, BATCH_SIZE):
        batch_count = min(BATCH_SIZE, TOTAL_SIMS - batch_start)
        configs = build_configs(batch_start, batch_count)
        result = amm_sim_rs.run_batch(
            list(user._bytecode),
            list(baseline._bytecode),
            configs,
            n_workers,
        )
        all_results.extend(result.results)

    # Extract arrays
    sub_edges = np.array([r.edges["submission"] for r in all_results])
    norm_edges = np.array([r.edges["normalizer"] for r in all_results])
    sub_arb = np.array([r.arb_edges["submission"] for r in all_results])
    norm_arb = np.array([r.arb_edges["normalizer"] for r in all_results])
    sub_retail = np.array([r.retail_edges["submission"] for r in all_results])
    norm_retail = np.array([r.retail_edges["normalizer"] for r in all_results])
    sub_arb_vol = np.array([r.arb_volume_y["submission"] for r in all_results])
    norm_arb_vol = np.array([r.arb_volume_y["normalizer"] for r in all_results])
    sub_retail_vol = np.array([r.retail_volume_y["submission"] for r in all_results])
    norm_retail_vol = np.array([r.retail_volume_y["normalizer"] for r in all_results])
    sub_avg_bid = np.array([r.average_fees["submission"][0] for r in all_results])
    sub_avg_ask = np.array([r.average_fees["submission"][1] for r in all_results])
    norm_avg_bid = np.array([r.average_fees["normalizer"][0] for r in all_results])
    norm_avg_ask = np.array([r.average_fees["normalizer"][1] for r in all_results])
    sub_pnl = np.array([r.pnl["submission"] for r in all_results])
    norm_pnl = np.array([r.pnl["normalizer"] for r in all_results])

    wins = np.sum(sub_edges > norm_edges)

    # Print report
    print(f"\n{'='*60}")
    print(f"  {name} — {TOTAL_SIMS} sims")
    print(f"{'='*60}")
    print(f"  Edge:          {sub_edges.mean():>8.2f}  (normalizer: {norm_edges.mean():.2f})")
    print(f"  Arb edge:      {sub_arb.mean():>8.2f}  (normalizer: {norm_arb.mean():.2f})")
    print(f"  Retail edge:   {sub_retail.mean():>8.2f}  (normalizer: {norm_retail.mean():.2f})")
    print(f"  Edge std:      {sub_edges.std():>8.2f}  (normalizer: {norm_edges.std():.2f})")
    print(f"  Win rate:      {wins:>5d}/100")
    print(f"  PnL:           {sub_pnl.mean():>8.2f}  (normalizer: {norm_pnl.mean():.2f})")
    print()
    print(f"  Retail vol:    {sub_retail_vol.mean():>8.0f}  (normalizer: {norm_retail_vol.mean():.0f})")
    ret_share = sub_retail_vol / (sub_retail_vol + norm_retail_vol)
    print(f"  Retail share:  {ret_share.mean()*100:>7.2f}%")
    print(f"  Arb vol:       {sub_arb_vol.mean():>8.0f}  (normalizer: {norm_arb_vol.mean():.0f})")
    arb_share = sub_arb_vol / (sub_arb_vol + norm_arb_vol)
    print(f"  Arb share:     {arb_share.mean()*100:>7.2f}%")
    print()
    sub_mid = (sub_avg_bid + sub_avg_ask) / 2
    norm_mid = (norm_avg_bid + norm_avg_ask) / 2
    print(f"  Avg bid fee:   {sub_avg_bid.mean()*1e4:>7.1f} bps  (normalizer: {norm_avg_bid.mean()*1e4:.1f} bps)")
    print(f"  Avg ask fee:   {sub_avg_ask.mean()*1e4:>7.1f} bps  (normalizer: {norm_avg_ask.mean()*1e4:.1f} bps)")
    print(f"  Avg mid fee:   {sub_mid.mean()*1e4:>7.1f} bps  (normalizer: {norm_mid.mean()*1e4:.1f} bps)")
    print()
    # Edge efficiency: retail edge per unit retail volume
    eff = sub_retail.mean() / sub_retail_vol.mean() * 1e4
    norm_eff = norm_retail.mean() / norm_retail_vol.mean() * 1e4
    print(f"  Retail edge/vol: {eff:>6.2f} bps  (normalizer: {norm_eff:.2f} bps)")
    arb_cost = -sub_arb.mean() / sub_arb_vol.mean() * 1e4 if sub_arb_vol.mean() > 0 else 0
    norm_arb_cost = -norm_arb.mean() / norm_arb_vol.mean() * 1e4 if norm_arb_vol.mean() > 0 else 0
    print(f"  Arb cost/vol:    {arb_cost:>6.2f} bps  (normalizer: {norm_arb_cost:.2f} bps)")
    print()
    # Per-sim edge percentiles
    pcts = [5, 25, 50, 75, 95]
    vals = np.percentile(sub_edges, pcts)
    pct_str = "  ".join(f"p{p}={v:.0f}" for p, v in zip(pcts, vals))
    print(f"  Edge dist:     {pct_str}")
    print(f"{'='*60}\n")

    return {
        "name": name,
        "edge": sub_edges.mean(),
        "arb_edge": sub_arb.mean(),
        "retail_edge": sub_retail.mean(),
        "retail_share": ret_share.mean(),
        "arb_share": arb_share.mean(),
        "avg_fee_bps": sub_mid.mean() * 1e4,
        "win_rate": wins / 100,
    }

if __name__ == "__main__":
    sol_path = sys.argv[1] if len(sys.argv) > 1 else "contracts/src/Strategy.sol"
    label = sys.argv[2] if len(sys.argv) > 2 else None
    run_diagnostics(sol_path, label)
