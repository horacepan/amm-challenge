"""Push vol_boost and linear even further."""
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
        'carry_min': 28, 'carry_scale': 25, 'carry_max': 55,
        'ema_retain': 98, 'ema_alpha': 2,
        'vol_alpha': 50, 'vol_boost': 55,
        'base_fee': 18, 'linear_coef': 7800, 'quad_coef': 60000,
    }
    defaults.update(overrides)
    code = SMOOTH_TEMPLATE.format(**defaults)
    score = score_strategy(code, N_SIMS)
    print(f"  {name}: {score:.2f}")
    return score, defaults


if __name__ == "__main__":
    best = 477.59
    best_p = {}

    print("=== Verify current best ===")
    s, p = test("current_best")
    if s > best: best, best_p = s, p

    # Push vb + linear together
    print("\n=== VB + Linear grid ===")
    for vb in [50, 55, 60, 65, 70, 75, 80]:
        for lc in [6000, 6500, 7000, 7500, 7800, 8000]:
            s, p = test(f"vb{vb}+lin{lc}", vol_boost=vb, linear_coef=lc)
            if s > best: best, best_p = s, p

    print(f"\nBest vb+lin: {best:.2f}, params vb={best_p.get('vol_boost')}, lin={best_p.get('linear_coef')}")
    bvb = best_p.get('vol_boost', 55)
    blc = best_p.get('linear_coef', 7800)

    # Retune quad at new vb+lin
    print(f"\n=== Quad retune (vb={bvb}, lin={blc}) ===")
    for qc in [40000, 50000, 55000, 60000, 65000, 70000, 80000]:
        s, p = test(f"q{qc}", vol_boost=bvb, linear_coef=blc, quad_coef=qc)
        if s > best: best, best_p = s, p
    bqc = best_p.get('quad_coef', 60000)

    # Retune base_fee
    print(f"\n=== Base fee retune ===")
    for bf in [14, 16, 17, 18, 19, 20, 22]:
        s, p = test(f"bf{bf}", vol_boost=bvb, linear_coef=blc, quad_coef=bqc, base_fee=bf)
        if s > best: best, best_p = s, p
    bbf = best_p.get('base_fee', 18)

    # Retune carry
    print(f"\n=== Carry retune ===")
    for cm in [25, 28, 30, 32]:
        for cx in [50, 55, 60]:
            for cs in [20, 25, 30]:
                s, p = test(f"cm{cm}_cx{cx}_cs{cs}", vol_boost=bvb, linear_coef=blc, quad_coef=bqc,
                           base_fee=bbf, carry_min=cm, carry_max=cx, carry_scale=cs)
                if s > best: best, best_p = s, p

    print(f"\n\n=== FINAL BEST: {best:.2f} ===")
    print(f"Params: {best_p}")
