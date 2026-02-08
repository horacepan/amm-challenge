"""Final fine-tuning around the 476.39 optimum."""
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
        'carry_min': 32, 'carry_scale': 20, 'carry_max': 55,
        'ema_retain': 97, 'ema_alpha': 3,
        'vol_alpha': 50, 'vol_boost': 45,
        'base_fee': 18, 'linear_coef': 8000, 'quad_coef': 65000,
    }
    defaults.update(overrides)
    code = SMOOTH_TEMPLATE.format(**defaults)
    score = score_strategy(code, N_SIMS)
    print(f"  {name}: {score:.2f}")
    return score, defaults


if __name__ == "__main__":
    best = 476.39
    best_p = {}

    print("=== Verify current best ===")
    s, p = test("current_best")
    if s > best: best, best_p = s, p

    # Push vb even higher at this new lower linear
    print("\n=== Vol boost re-tune at lin8000 ===")
    for vb in [40, 42, 44, 45, 46, 48, 50, 52, 55]:
        s, p = test(f"vb{vb}", vol_boost=vb)
        if s > best: best, best_p = s, p
    bvb = best_p.get('vol_boost', 45)

    # EMA even slower
    print(f"\n=== EMA tune (vb={bvb}) ===")
    for er, ea in [(96, 4), (97, 3), (98, 2)]:
        s, p = test(f"ema{er}_{ea}", vol_boost=bvb, ema_retain=er, ema_alpha=ea)
        if s > best: best, best_p = s, p
    ber = best_p.get('ema_retain', 97)
    bea = best_p.get('ema_alpha', 3)

    # Linear fine tune
    print(f"\n=== Linear fine tune (vb={bvb}, ema={ber}/{bea}) ===")
    for lc in [7500, 7700, 7800, 8000, 8200, 8300, 8500]:
        s, p = test(f"lin{lc}", vol_boost=bvb, ema_retain=ber, ema_alpha=bea, linear_coef=lc)
        if s > best: best, best_p = s, p
    blc = best_p.get('linear_coef', 8000)

    # Quad fine tune
    print(f"\n=== Quad fine tune ===")
    for qc in [55000, 60000, 62000, 65000, 68000, 70000, 75000]:
        s, p = test(f"q{qc}", vol_boost=bvb, ema_retain=ber, ema_alpha=bea, linear_coef=blc, quad_coef=qc)
        if s > best: best, best_p = s, p
    bqc = best_p.get('quad_coef', 65000)

    # Base fee
    print(f"\n=== Base fee ===")
    for bf in [15, 16, 17, 18, 19, 20]:
        s, p = test(f"bf{bf}", vol_boost=bvb, ema_retain=ber, ema_alpha=bea, linear_coef=blc, quad_coef=bqc, base_fee=bf)
        if s > best: best, best_p = s, p
    bbf = best_p.get('base_fee', 18)

    # Vol alpha
    print(f"\n=== Vol alpha ===")
    for va in [40, 45, 48, 50, 52, 55, 60]:
        s, p = test(f"va{va}", vol_boost=bvb, ema_retain=ber, ema_alpha=bea, linear_coef=blc, quad_coef=bqc, base_fee=bbf, vol_alpha=va)
        if s > best: best, best_p = s, p
    bva = best_p.get('vol_alpha', 50)

    # Carry
    print(f"\n=== Carry fine tune ===")
    for cm in [28, 30, 32, 34]:
        for cx in [50, 55, 60]:
            for cs in [15, 20, 25]:
                s, p = test(f"cm{cm}_cx{cx}_cs{cs}", vol_boost=bvb, ema_retain=ber, ema_alpha=bea,
                           linear_coef=blc, quad_coef=bqc, base_fee=bbf, vol_alpha=bva,
                           carry_min=cm, carry_max=cx, carry_scale=cs)
                if s > best: best, best_p = s, p

    print(f"\n\n=== FINAL BEST: {best:.2f} ===")
    print(f"Params: {best_p}")
