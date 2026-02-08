"""Validate key strategies at 35 sims to check robustness."""
from sweep import score_strategy

N_SIMS = 35

ORIGINAL = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";
contract Strategy is AMMStrategyBase {
    function afterInitialize(uint256, uint256) external override returns (uint256, uint256) {
        slots[2] = WAD / 200;
        return (bpsToWad(30), bpsToWad(30));
    }
    function afterSwap(TradeInfo calldata trade) external override returns (uint256, uint256) {
        uint256 impact = wdiv(trade.amountY, trade.reserveY);
        if (trade.timestamp != slots[0]) {
            slots[0] = trade.timestamp;
            uint256 carry = slots[1] < WAD / 200 ? WAD * 33 / 100 : WAD * 45 / 100;
            slots[1] = wmul(slots[1], carry) + impact;
        } else {
            slots[1] = slots[1] + impact;
        }
        slots[2] = wmul(slots[2], WAD * 93 / 100) + wmul(impact, WAD * 7 / 100);
        uint256 alpha = WAD * 50 / 100;
        slots[3] = wmul(slots[3], WAD - alpha) + wmul(impact, alpha);
        slots[4] = wmul(slots[4], WAD - alpha) + wmul(wmul(impact, impact), alpha);
        uint256 m1sq = wmul(slots[3], slots[3]);
        uint256 variance = slots[4] > m1sq ? slots[4] - m1sq : 0;
        uint256 vol = sqrt(variance * WAD);
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 boostedSignal = signal + wmul(vol, WAD * 20 / 100);
        uint256 fee = bpsToWad(20) + wmul(boostedSignal, bpsToWad(9500)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(65000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "Original"; }
}
"""

# Template for smooth decay with params
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

def make_strategy(**overrides):
    defaults = {
        'carry_min': 22, 'carry_scale': 35, 'carry_max': 60,
        'ema_retain': 99, 'ema_alpha': 1,
        'vol_alpha': 40, 'vol_boost': 500,
        'base_fee': 16, 'linear_coef': 3800, 'quad_coef': 7000,
    }
    defaults.update(overrides)
    return SMOOTH_TEMPLATE.format(**defaults)


print("=== Validating at 35 sims ===")
print(f"  Original VolBoost: {score_strategy(ORIGINAL, N_SIMS):.2f}")
print(f"  V2 vb500+lin3800+q7000: {score_strategy(make_strategy(), N_SIMS):.2f}")
print(f"  V2 vb450+lin4000+q8000: {score_strategy(make_strategy(vol_boost=450, linear_coef=4000, quad_coef=8000), N_SIMS):.2f}")
print(f"  V2 vb400+lin4000+q10000: {score_strategy(make_strategy(vol_boost=400, linear_coef=4000, quad_coef=10000, base_fee=18), N_SIMS):.2f}")
print(f"  V2 vb300+lin5000+q10000: {score_strategy(make_strategy(vol_boost=300, linear_coef=5000, quad_coef=10000, base_fee=17, carry_min=28, carry_max=55), N_SIMS):.2f}")
print(f"  V2 vb200+lin6000+q20000: {score_strategy(make_strategy(vol_boost=200, linear_coef=6000, quad_coef=20000, base_fee=17), N_SIMS):.2f}")

# Quick sweep of top combos at 35 sims
print("\n=== Top combos at 35 sims ===")
best = 0
for vb, lc, qc in [(500, 3800, 7000), (550, 3500, 7000), (450, 4200, 9000),
                     (475, 4000, 7000), (425, 4200, 9000), (600, 3500, 3000),
                     (400, 4500, 12000), (350, 4500, 12000)]:
    s = score_strategy(make_strategy(vol_boost=vb, linear_coef=lc, quad_coef=qc), N_SIMS)
    print(f"  vb{vb}+lin{lc}+q{qc}: {s:.2f}")
    if s > best: best = s
print(f"\nBest at 35 sims: {best:.2f}")
