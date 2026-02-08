"""Deep search around best combos + structural improvements."""
from sweep import score_strategy

N_SIMS = 30

# Template with smooth decay (carry interpolation instead of binary switch)
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
    function getName() external pure override returns (string memory) {{ return "DeepSearch"; }}
}}
"""

# Standard template (binary carry)
STANDARD_TEMPLATE = """// SPDX-License-Identifier: MIT
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
    function getName() external pure override returns (string memory) {{ return "DeepSearch"; }}
}}
"""


def test_standard(name, **p):
    defaults = {
        'calm_carry': 33, 'turb_carry': 45,
        'ema_retain': 93, 'ema_alpha': 7,
        'vol_alpha': 50, 'vol_boost': 20,
        'base_fee': 20, 'linear_coef': 9500, 'quad_coef': 65000,
    }
    defaults.update(p)
    code = STANDARD_TEMPLATE.format(**defaults)
    score = score_strategy(code, N_SIMS)
    print(f"  {name}: {score:.2f}  (delta: {score - 472.61:+.2f})")
    return score


def test_smooth(name, **p):
    defaults = {
        'carry_min': 30, 'carry_scale': 20, 'carry_max': 50,
        'ema_retain': 93, 'ema_alpha': 7,
        'vol_alpha': 50, 'vol_boost': 20,
        'base_fee': 20, 'linear_coef': 9500, 'quad_coef': 65000,
    }
    defaults.update(p)
    code = SMOOTH_TEMPLATE.format(**defaults)
    score = score_strategy(code, N_SIMS)
    print(f"  {name}: {score:.2f}  (delta: {score - 472.61:+.2f})")
    return score


if __name__ == "__main__":
    print("=== Standard template - fine search around bf18+lin9000+q65k (473.23) ===")
    best_std = 472.61
    best_std_params = {}

    configs = [
        ("bf18+lin9000+q65k", dict(base_fee=18, linear_coef=9000)),
        ("bf18+lin9000+q60k", dict(base_fee=18, linear_coef=9000, quad_coef=60000)),
        ("bf18+lin9000+q70k", dict(base_fee=18, linear_coef=9000, quad_coef=70000)),
        ("bf18+lin9100+q65k", dict(base_fee=18, linear_coef=9100)),
        ("bf18+lin8900+q65k", dict(base_fee=18, linear_coef=8900)),
        ("bf17+lin9000+q65k", dict(base_fee=17, linear_coef=9000)),
        ("bf19+lin9000+q65k", dict(base_fee=19, linear_coef=9000)),
        # Try with carry tuning
        ("bf18+lin9000+c30t45", dict(base_fee=18, linear_coef=9000, calm_carry=30, turb_carry=45)),
        ("bf18+lin9000+c30t50", dict(base_fee=18, linear_coef=9000, calm_carry=30, turb_carry=50)),
        ("bf18+lin9000+c33t50", dict(base_fee=18, linear_coef=9000, calm_carry=33, turb_carry=50)),
        # Try with vol params
        ("bf18+lin9000+vb25", dict(base_fee=18, linear_coef=9000, vol_boost=25)),
        ("bf18+lin9000+vb15", dict(base_fee=18, linear_coef=9000, vol_boost=15)),
        ("bf18+lin9000+va40", dict(base_fee=18, linear_coef=9000, vol_alpha=40)),
        ("bf18+lin9000+va60", dict(base_fee=18, linear_coef=9000, vol_alpha=60)),
        # Multi-param combos
        ("bf18+lin9000+vb25+c30t50", dict(base_fee=18, linear_coef=9000, vol_boost=25, calm_carry=30, turb_carry=50)),
        ("bf18+lin9000+vb25+c30t45", dict(base_fee=18, linear_coef=9000, vol_boost=25, calm_carry=30, turb_carry=45)),
        ("bf18+lin9000+ema94_6", dict(base_fee=18, linear_coef=9000, ema_retain=94, ema_alpha=6)),
        ("bf18+lin9000+ema95_5", dict(base_fee=18, linear_coef=9000, ema_retain=95, ema_alpha=5)),
    ]

    for name, params in configs:
        s = test_standard(name, **params)
        if s > best_std:
            best_std = s
            best_std_params = params

    print(f"\nBest standard: {best_std:.2f}, params: {best_std_params}")

    print("\n=== Smooth decay template ===")
    best_smooth = 472.61
    best_smooth_params = {}

    smooth_configs = [
        ("smooth_default", {}),
        ("smooth+bf18+lin9000", dict(base_fee=18, linear_coef=9000)),
        ("smooth+bf18+lin9000+q60k", dict(base_fee=18, linear_coef=9000, quad_coef=60000)),
        ("smooth+bf18+lin9000+vb25", dict(base_fee=18, linear_coef=9000, vol_boost=25)),
        ("smooth+bf18+lin9000+cm28", dict(base_fee=18, linear_coef=9000, carry_min=28)),
        ("smooth+bf18+lin9000+cm32", dict(base_fee=18, linear_coef=9000, carry_min=32)),
        ("smooth+bf18+lin9000+cx55", dict(base_fee=18, linear_coef=9000, carry_max=55)),
        ("smooth+bf18+lin9000+cx45", dict(base_fee=18, linear_coef=9000, carry_max=45)),
        ("smooth+bf18+lin9000+cs15", dict(base_fee=18, linear_coef=9000, carry_scale=15)),
        ("smooth+bf18+lin9000+cs25", dict(base_fee=18, linear_coef=9000, carry_scale=25)),
    ]

    for name, params in smooth_configs:
        s = test_smooth(name, **params)
        if s > best_smooth:
            best_smooth = s
            best_smooth_params = params

    print(f"\nBest smooth: {best_smooth:.2f}, params: {best_smooth_params}")
