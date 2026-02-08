"""Ultra-final push with extreme vol boost."""
from sweep import score_strategy

N_SIMS = 30

SMOOTH_TEMPLATE = """// SPDX-License-Identifier: MIT
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
            uint256 level = slots[1] < WAD / 100 ? slots[1] : WAD / 100;
            uint256 carry = WAD * {carry_min} / 100 + wmul(level, WAD * {carry_scale});
            if (carry > WAD * {carry_max} / 100) carry = WAD * {carry_max} / 100;
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
    function getName() external pure override returns (string memory) {{ return "VolBoostV2"; }}
}}
"""


def test(name, **overrides):
    defaults = {
        'carry_min': 22, 'carry_scale': 35, 'carry_max': 60,
        'ema_retain': 99, 'ema_alpha': 1,
        'vol_alpha': 40, 'vol_boost': 500,
        'base_fee': 16, 'linear_coef': 3800, 'quad_coef': 7000,
    }
    defaults.update(overrides)
    code = SMOOTH_TEMPLATE.format(**defaults)
    score = score_strategy(code, N_SIMS)
    print(f"  {name}: {score:.2f}")
    return score, defaults


if __name__ == "__main__":
    best = 486.99
    best_p = {}

    print("=== Higher VB with lower linear/quad ===")
    for vb in [500, 550, 600, 700, 800, 1000]:
        for lc in [2500, 3000, 3500, 3800, 4000]:
            for qc in [3000, 5000, 7000, 10000]:
                s, p = test(f"vb{vb}+lin{lc}+q{qc}", vol_boost=vb, linear_coef=lc, quad_coef=qc)
                if s > best: best, best_p = s, p

    print(f"\nBest: {best:.2f}")
    print(f"Params: {best_p}")

    if best > 486.99:
        bvb = best_p.get('vol_boost', 500)
        blc = best_p.get('linear_coef', 3800)
        bqc = best_p.get('quad_coef', 7000)
        for bf in [14, 15, 16, 17]:
            s, p = test(f"bf{bf}", vol_boost=bvb, linear_coef=blc, quad_coef=bqc, base_fee=bf)
            if s > best: best, best_p = s, p
        for va in [35, 38, 40, 42, 45]:
            s, p = test(f"va{va}", vol_boost=bvb, linear_coef=blc, quad_coef=bqc,
                       base_fee=best_p.get('base_fee', 16), vol_alpha=va)
            if s > best: best, best_p = s, p

    print(f"\n\n=== ABSOLUTE BEST: {best:.2f} ===")
    print(f"Params: {best_p}")
