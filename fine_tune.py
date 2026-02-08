"""Fine-tune around the best found strategy."""
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
    function getName() external pure override returns (string memory) {{ return "FineTune"; }}
}}
"""


def test(name, **overrides):
    defaults = {
        'carry_min': 30, 'carry_scale': 20, 'carry_max': 50,
        'ema_retain': 93, 'ema_alpha': 7,
        'vol_alpha': 50, 'vol_boost': 25,
        'base_fee': 18, 'linear_coef': 9000, 'quad_coef': 65000,
    }
    defaults.update(overrides)
    code = SMOOTH_TEMPLATE.format(**defaults)
    score = score_strategy(code, N_SIMS)
    print(f"  {name}: {score:.2f}  (delta: {score - 472.61:+.2f})")
    return score, defaults


if __name__ == "__main__":
    best_score = 474.20
    best_params = {}

    print("=== Current best: smooth+bf18+lin9000+vb25 = 474.20 ===")
    s, p = test("baseline_smooth")
    if s > best_score:
        best_score = s
        best_params = p

    print("\n=== Vol boost fine-tuning ===")
    for vb in [22, 23, 24, 25, 26, 27, 28, 30, 35]:
        s, p = test(f"vb{vb}", vol_boost=vb)
        if s > best_score:
            best_score = s
            best_params = p

    print("\n=== Base fee fine-tuning ===")
    for bf in [15, 16, 17, 18, 19, 20]:
        s, p = test(f"bf{bf}", base_fee=bf)
        if s > best_score:
            best_score = s
            best_params = p

    print("\n=== Linear coef fine-tuning ===")
    for lc in [8500, 8700, 8800, 9000, 9100, 9200, 9300, 9500]:
        s, p = test(f"lin{lc}", linear_coef=lc)
        if s > best_score:
            best_score = s
            best_params = p

    print("\n=== Quad coef fine-tuning ===")
    for qc in [50000, 55000, 60000, 65000, 70000, 75000]:
        s, p = test(f"q{qc}", quad_coef=qc)
        if s > best_score:
            best_score = s
            best_params = p

    print("\n=== Carry parameters ===")
    for cm in [25, 28, 30, 32]:
        for cx in [45, 50, 55, 60]:
            for cs in [15, 20, 25, 30]:
                s, p = test(f"cm{cm}_cx{cx}_cs{cs}", carry_min=cm, carry_max=cx, carry_scale=cs)
                if s > best_score:
                    best_score = s
                    best_params = p

    print("\n=== Vol alpha ===")
    for va in [35, 40, 45, 50, 55, 60, 65]:
        s, p = test(f"va{va}", vol_alpha=va)
        if s > best_score:
            best_score = s
            best_params = p

    print("\n=== EMA params ===")
    for er, ea in [(91, 9), (92, 8), (93, 7), (94, 6), (95, 5), (96, 4)]:
        s, p = test(f"ema{er}_{ea}", ema_retain=er, ema_alpha=ea)
        if s > best_score:
            best_score = s
            best_params = p

    print(f"\n\n=== BEST FOUND: {best_score:.2f} ===")
    print(f"Params: {best_params}")
