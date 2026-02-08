"""Push vol_boost higher and combine all best params."""
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
        'carry_min': 30, 'carry_scale': 20, 'carry_max': 50,
        'ema_retain': 93, 'ema_alpha': 7,
        'vol_alpha': 50, 'vol_boost': 35,
        'base_fee': 18, 'linear_coef': 9000, 'quad_coef': 65000,
    }
    defaults.update(overrides)
    code = SMOOTH_TEMPLATE.format(**defaults)
    score = score_strategy(code, N_SIMS)
    print(f"  {name}: {score:.2f}")
    return score, defaults


if __name__ == "__main__":
    best = 474.99
    best_p = {}

    print("=== Push vol_boost higher ===")
    for vb in [35, 40, 45, 50, 55, 60, 70, 80, 100]:
        s, p = test(f"vb{vb}", vol_boost=vb)
        if s > best: best, best_p = s, p

    print("\n=== At best vb, tune other params ===")
    # Using whatever vb was best, tune other params
    print(f"Best vb so far: {best:.2f}")

    # Re-tune linear with high vb
    for lc in [7000, 8000, 8500, 9000, 9500, 10000, 11000]:
        s, p = test(f"best_vb+lin{lc}", vol_boost=best_p.get('vol_boost', 35), linear_coef=lc)
        if s > best: best, best_p = s, p

    print(f"\nBest so far: {best:.2f}, params: {best_p}")

    # Re-tune quad with high vb + best linear
    bvb = best_p.get('vol_boost', 35)
    blc = best_p.get('linear_coef', 9000)
    for qc in [40000, 50000, 60000, 65000, 70000, 80000, 100000]:
        s, p = test(f"vb{bvb}+lin{blc}+q{qc}", vol_boost=bvb, linear_coef=blc, quad_coef=qc)
        if s > best: best, best_p = s, p

    print(f"\nBest so far: {best:.2f}, params: {best_p}")

    # Re-tune base fee
    bqc = best_p.get('quad_coef', 65000)
    for bf in [12, 15, 18, 20, 22, 25]:
        s, p = test(f"vb{bvb}+lin{blc}+q{bqc}+bf{bf}", vol_boost=bvb, linear_coef=blc, quad_coef=bqc, base_fee=bf)
        if s > best: best, best_p = s, p

    # Re-tune carry
    bbf = best_p.get('base_fee', 18)
    for cm in [25, 28, 30, 32]:
        for cx in [45, 50, 55]:
            s, p = test(f"cm{cm}_cx{cx}", vol_boost=bvb, linear_coef=blc, quad_coef=bqc, base_fee=bbf, carry_min=cm, carry_max=cx)
            if s > best: best, best_p = s, p

    # Re-tune EMA
    bcm = best_p.get('carry_min', 30)
    bcx = best_p.get('carry_max', 50)
    for er, ea in [(93, 7), (94, 6), (95, 5), (96, 4), (97, 3)]:
        s, p = test(f"ema{er}_{ea}", vol_boost=bvb, linear_coef=blc, quad_coef=bqc, base_fee=bbf,
                    carry_min=bcm, carry_max=bcx, ema_retain=er, ema_alpha=ea)
        if s > best: best, best_p = s, p

    # Re-tune vol_alpha
    ber = best_p.get('ema_retain', 93)
    bea = best_p.get('ema_alpha', 7)
    for va in [35, 40, 45, 50, 55, 60]:
        s, p = test(f"va{va}", vol_boost=bvb, linear_coef=blc, quad_coef=bqc, base_fee=bbf,
                    carry_min=bcm, carry_max=bcx, ema_retain=ber, ema_alpha=bea, vol_alpha=va)
        if s > best: best, best_p = s, p

    print(f"\n\n=== FINAL BEST: {best:.2f} ===")
    print(f"Params: {best_p}")
