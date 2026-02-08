"""Parameter sweep script for AMM strategy optimization."""
import sys
import time
from pathlib import Path

from amm_competition.competition.match import MatchRunner, HyperparameterVariance
from amm_competition.evm.adapter import EVMStrategyAdapter
from amm_competition.evm.baseline import load_vanilla_strategy
from amm_competition.evm.compiler import SolidityCompiler
from amm_competition.competition.config import (
    BASELINE_SETTINGS,
    BASELINE_VARIANCE,
    baseline_nominal_retail_rate,
    baseline_nominal_retail_size,
    baseline_nominal_sigma,
    resolve_n_workers,
)
import amm_sim_rs

N_SIMS = 30  # 30 sims for decent reliability without segfault

STRATEGY_TEMPLATE = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {{AMMStrategyBase}} from "./AMMStrategyBase.sol";
import {{TradeInfo}} from "./IAMMStrategy.sol";
contract Strategy is AMMStrategyBase {{
    function afterInitialize(uint256, uint256) external override returns (uint256, uint256) {{
        slots[2] = WAD / 200;
        return (bpsToWad(30), bpsToWad(30));
    }}
    function afterSwap(TradeInfo calldata trade) external override returns (uint256, uint256) {{
        uint256 impact = wdiv(trade.amountY, trade.reserveY);
        if (trade.timestamp != slots[0]) {{
            slots[0] = trade.timestamp;
            uint256 carry = slots[1] < WAD / 200 ? WAD * {calm_carry} / 100 : WAD * {turb_carry} / 100;
            slots[1] = wmul(slots[1], carry) + impact;
        }} else {{
            slots[1] = slots[1] + impact;
        }}
        slots[2] = wmul(slots[2], WAD * {ema_retain} / 100) + wmul(impact, WAD * {ema_alpha} / 100);
        uint256 alpha = WAD * {vol_alpha} / 100;
        slots[3] = wmul(slots[3], WAD - alpha) + wmul(impact, alpha);
        slots[4] = wmul(slots[4], WAD - alpha) + wmul(wmul(impact, impact), alpha);
        uint256 m1sq = wmul(slots[3], slots[3]);
        uint256 variance = slots[4] > m1sq ? slots[4] - m1sq : 0;
        uint256 vol = sqrt(variance * WAD);
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 boostedSignal = signal + wmul(vol, WAD * {vol_boost} / 100);
        uint256 fee = bpsToWad({base_fee}) + wmul(boostedSignal, bpsToWad({linear_coef})) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad({quad_coef}));
        return (clampFee(fee), clampFee(fee));
    }}
    function getName() external pure override returns (string memory) {{ return "Sweep"; }}
}}
"""


def score_strategy(source_code: str, n_sims: int = N_SIMS) -> float:
    """Compile and score a strategy, returning edge."""
    compiler = SolidityCompiler()
    compilation = compiler.compile(source_code)
    if not compilation.success:
        print(f"  COMPILE ERROR: {compilation.errors}")
        return -9999.0

    user_strategy = EVMStrategyAdapter(
        bytecode=compilation.bytecode,
        abi=compilation.abi,
    )
    default_strategy = load_vanilla_strategy()

    config = amm_sim_rs.SimulationConfig(
        n_steps=BASELINE_SETTINGS.n_steps,
        initial_price=BASELINE_SETTINGS.initial_price,
        initial_x=BASELINE_SETTINGS.initial_x,
        initial_y=BASELINE_SETTINGS.initial_y,
        gbm_mu=BASELINE_SETTINGS.gbm_mu,
        gbm_sigma=baseline_nominal_sigma(),
        gbm_dt=BASELINE_SETTINGS.gbm_dt,
        retail_arrival_rate=baseline_nominal_retail_rate(),
        retail_mean_size=baseline_nominal_retail_size(),
        retail_size_sigma=BASELINE_SETTINGS.retail_size_sigma,
        retail_buy_prob=BASELINE_SETTINGS.retail_buy_prob,
        seed=None,
    )

    runner = MatchRunner(
        n_simulations=n_sims,
        config=config,
        n_workers=resolve_n_workers(),
        variance=BASELINE_VARIANCE,
    )
    result = runner.run_match(user_strategy, default_strategy)
    avg_edge = float(result.total_edge_a / n_sims)
    return avg_edge


def score_from_file(filepath: str, n_sims: int = N_SIMS) -> float:
    """Score a strategy from a .sol file."""
    source = Path(filepath).read_text()
    return score_strategy(source, n_sims)


def run_param_sweep():
    """Run a parameter sweep over key parameters."""
    # Current best params
    best_params = {
        'calm_carry': 33, 'turb_carry': 45,
        'ema_retain': 93, 'ema_alpha': 7,
        'vol_alpha': 50, 'vol_boost': 20,
        'base_fee': 20, 'linear_coef': 9500, 'quad_coef': 65000,
    }

    # Score the baseline
    baseline_code = STRATEGY_TEMPLATE.format(**best_params)
    baseline_score = score_strategy(baseline_code)
    print(f"BASELINE: {baseline_score:.2f}")
    print()

    best_score = baseline_score
    best_combo = dict(best_params)

    # Define sweep ranges for each parameter
    sweeps = {
        'base_fee': [10, 15, 18, 20, 22, 25, 30],
        'linear_coef': [7000, 8000, 9000, 9500, 10000, 11000, 12000],
        'quad_coef': [40000, 50000, 55000, 60000, 65000, 70000, 80000, 100000],
        'vol_boost': [10, 15, 20, 25, 30, 40, 50],
        'vol_alpha': [30, 40, 50, 60, 70],
        'calm_carry': [25, 30, 33, 36, 40],
        'turb_carry': [35, 40, 45, 50, 55],
        'ema_retain': [90, 92, 93, 94, 95, 96],
        'ema_alpha': [5, 7, 9, 10, 12],
    }

    # Single-parameter sweeps
    for param_name, values in sweeps.items():
        print(f"--- Sweeping {param_name} ---")
        for val in values:
            params = dict(best_combo)
            params[param_name] = val
            code = STRATEGY_TEMPLATE.format(**params)
            score = score_strategy(code)
            marker = " ***" if score > best_score else ""
            print(f"  {param_name}={val}: {score:.2f}{marker}")
            if score > best_score:
                best_score = score
                best_combo = dict(params)
        print()

    print(f"\nBEST SCORE: {best_score:.2f}")
    print(f"BEST PARAMS: {best_combo}")
    return best_combo, best_score


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "file":
        filepath = sys.argv[2]
        n = int(sys.argv[3]) if len(sys.argv) > 3 else N_SIMS
        score = score_from_file(filepath, n)
        print(f"Edge: {score:.2f}")
    else:
        run_param_sweep()
