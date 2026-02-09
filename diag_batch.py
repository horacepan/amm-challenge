"""Run a single batch and output JSON stats."""
import sys
import json
import numpy as np
import amm_sim_rs
from amm_competition.evm.compiler import SolidityCompiler
from amm_competition.evm.adapter import EVMStrategyAdapter
from amm_competition.evm.baseline import load_vanilla_strategy
from amm_competition.competition.config import (
    BASELINE_SETTINGS, BASELINE_VARIANCE, resolve_n_workers,
)

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

sol_path = sys.argv[1]
start = int(sys.argv[2])
count = int(sys.argv[3])

source_code = open(sol_path).read()
compiler = SolidityCompiler()
compilation = compiler.compile(source_code)
user = EVMStrategyAdapter(bytecode=compilation.bytecode, abi=compilation.abi)
baseline = load_vanilla_strategy()

configs = build_configs(start, count)
result = amm_sim_rs.run_batch(
    list(user._bytecode),
    list(baseline._bytecode),
    configs,
    resolve_n_workers(),
)

# Collect per-sim stats
stats = []
for r in result.results:
    stats.append({
        "edge": r.edges["submission"],
        "norm_edge": r.edges["normalizer"],
        "arb_edge": r.arb_edges["submission"],
        "norm_arb_edge": r.arb_edges["normalizer"],
        "retail_edge": r.retail_edges["submission"],
        "norm_retail_edge": r.retail_edges["normalizer"],
        "arb_vol": r.arb_volume_y["submission"],
        "norm_arb_vol": r.arb_volume_y["normalizer"],
        "retail_vol": r.retail_volume_y["submission"],
        "norm_retail_vol": r.retail_volume_y["normalizer"],
        "avg_bid": r.average_fees["submission"][0],
        "avg_ask": r.average_fees["submission"][1],
        "norm_avg_bid": r.average_fees["normalizer"][0],
        "norm_avg_ask": r.average_fees["normalizer"][1],
        "pnl": r.pnl["submission"],
        "norm_pnl": r.pnl["normalizer"],
    })
print(json.dumps(stats))
