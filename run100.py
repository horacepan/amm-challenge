"""Run 100 simulations in batches to avoid memory crash."""
import sys
import numpy as np
import amm_sim_rs
from amm_competition.evm.compiler import SolidityCompiler
from amm_competition.evm.adapter import EVMStrategyAdapter
from amm_competition.evm.baseline import load_vanilla_strategy
from amm_competition.competition.config import (
    BASELINE_SETTINGS, BASELINE_VARIANCE,
    baseline_nominal_sigma, baseline_nominal_retail_rate,
    baseline_nominal_retail_size, resolve_n_workers,
)

TOTAL_SIMS = 100
BATCH_SIZE = 25  # stays well under the 38 crash threshold

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

def run_strategy(sol_path):
    source_code = open(sol_path).read()
    compiler = SolidityCompiler()
    compilation = compiler.compile(source_code)
    if not compilation.success:
        print(f"Compile failed: {compilation.errors}")
        return None
    user = EVMStrategyAdapter(bytecode=compilation.bytecode, abi=compilation.abi)
    name = user.get_name()
    baseline = load_vanilla_strategy()

    total_edge = 0.0
    n_done = 0
    n_workers = resolve_n_workers()

    for batch_start in range(0, TOTAL_SIMS, BATCH_SIZE):
        batch_count = min(BATCH_SIZE, TOTAL_SIMS - batch_start)
        configs = build_configs(batch_start, batch_count)
        result = amm_sim_rs.run_batch(
            list(user._bytecode),
            list(baseline._bytecode),
            configs,
            n_workers,
        )
        for r in result.results:
            total_edge += r.edges["submission"]
        n_done += batch_count

    avg = total_edge / TOTAL_SIMS
    print(f"{name} Edge (100 sims): {avg:.2f}")
    return avg

if __name__ == "__main__":
    sol_path = sys.argv[1] if len(sys.argv) > 1 else "contracts/src/Strategy.sol"
    run_strategy(sol_path)
