"""Test radical strategy ideas to break through the 469 ceiling."""
import sys
from sweep import score_strategy

N_SIMS = 30

# Test 1: What if we charge MAX fee? The routing formula suggests we barely lose volume
MAX_FEE = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";
contract Strategy is AMMStrategyBase {
    function afterInitialize(uint256, uint256) external override returns (uint256, uint256) {
        return (MAX_FEE, MAX_FEE);
    }
    function afterSwap(TradeInfo calldata) external override returns (uint256, uint256) {
        return (MAX_FEE, MAX_FEE);
    }
    function getName() external pure override returns (string memory) { return "MaxFee"; }
}
"""

# Test 2: LOWER fees after arb, HIGHER before arb
# Key insight: within a step, arb comes first, then retail
# After arb (first trade of step, big impact): lower fee to attract retail
# After retail (subsequent trades): raise fee for next step's arb
ARB_FIRST = """// SPDX-License-Identifier: MIT
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

        bool isNewStep = trade.timestamp != slots[0];

        if (isNewStep) {
            slots[0] = trade.timestamp;
            uint256 carry = slots[1] < WAD / 200 ? WAD * 33 / 100 : WAD * 45 / 100;
            slots[1] = wmul(slots[1], carry) + impact;
            slots[5] = 1; // Mark: first trade of step (likely arb)
        } else {
            slots[1] = slots[1] + impact;
            slots[5] = 0; // Not first trade (likely retail)
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

        uint256 fee;
        if (slots[5] == 1) {
            // Just saw arb (or first trade of step). Set LOWER fee for retail coming next.
            fee = bpsToWad(15) + wmul(boostedSignal, bpsToWad(5000)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(30000));
        } else {
            // Just saw retail. Set HIGHER fee for next step's arb.
            fee = bpsToWad(25) + wmul(boostedSignal, bpsToWad(12000)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(80000));
        }
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "ArbFirst"; }
}
"""

# Test 3: Very high constant fee (300bps) - to see upper bound
HIGH_CONST = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";
contract Strategy is AMMStrategyBase {
    function afterInitialize(uint256, uint256) external override returns (uint256, uint256) {
        return (bpsToWad(300), bpsToWad(300));
    }
    function afterSwap(TradeInfo calldata) external override returns (uint256, uint256) {
        return (bpsToWad(300), bpsToWad(300));
    }
    function getName() external pure override returns (string memory) { return "High300"; }
}
"""

# Test 4: Dynamic with MUCH higher ceiling and steeper curve
STEEP_CURVE = """// SPDX-License-Identifier: MIT
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
        // Much steeper curve - higher fees across the board
        uint256 fee = bpsToWad(25) + wmul(boostedSignal, bpsToWad(15000)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(100000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "SteepCurve"; }
}
"""

# Test 5: Lower everything - lower base, gentler curve
GENTLE_CURVE = """// SPDX-License-Identifier: MIT
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
        // Gentler curve - lower everything
        uint256 fee = bpsToWad(15) + wmul(boostedSignal, bpsToWad(6000)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(40000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "GentleCurve"; }
}
"""

# Test 6: Impact-gated fee: only raise fee for LARGE impacts (likely arbs),
# ignore small impacts (retail) for signal accumulation
IMPACT_GATED = """// SPDX-License-Identifier: MIT
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

        // Only accumulate impact for "large" trades (likely arbs)
        // Threshold: 0.1% of reserves
        uint256 gatedImpact = impact > WAD / 1000 ? impact : 0;

        if (trade.timestamp != slots[0]) {
            slots[0] = trade.timestamp;
            uint256 carry = slots[1] < WAD / 200 ? WAD * 33 / 100 : WAD * 45 / 100;
            slots[1] = wmul(slots[1], carry) + gatedImpact;
        } else {
            slots[1] = slots[1] + gatedImpact;
        }
        slots[2] = wmul(slots[2], WAD * 93 / 100) + wmul(gatedImpact, WAD * 7 / 100);

        // Vol uses all impacts (including retail) for variance estimation
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
    function getName() external pure override returns (string memory) { return "ImpactGated"; }
}
"""

# Test 7: Separate arb-aware and retail-aware fee components
# After first trade of step (arb), set a "protection" fee
# After subsequent trades, blend protection with "attraction" fee
BLENDED_FEE = """// SPDX-License-Identifier: MIT
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
            // Store this step's arb impact for reference
            slots[5] = impact;
            slots[6] = 0; // trade count this step
        } else {
            slots[1] = slots[1] + impact;
            slots[6] = slots[6] + WAD;
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

        uint256 baseFee;
        if (slots[6] == 0) {
            // Just processed arb (first trade of step)
            // Lower fee for upcoming retail
            baseFee = bpsToWad(18);
        } else {
            // After retail - higher fee for next step's arb
            baseFee = bpsToWad(22);
        }
        uint256 fee = baseFee + wmul(boostedSignal, bpsToWad(9500)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(65000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "BlendedFee"; }
}
"""

strategies = {
    "MAX_FEE": MAX_FEE,
    "HIGH_CONST_300": HIGH_CONST,
    "STEEP_CURVE": STEEP_CURVE,
    "GENTLE_CURVE": GENTLE_CURVE,
    "ARB_FIRST": ARB_FIRST,
    "IMPACT_GATED": IMPACT_GATED,
    "BLENDED_FEE": BLENDED_FEE,
}

if __name__ == "__main__":
    n_sims = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    results = {}

    for name, code in strategies.items():
        print(f"Testing {name}...")
        try:
            score = score_strategy(code, n_sims)
            results[name] = score
            print(f"  {name}: {score:.2f}")
        except Exception as e:
            print(f"  {name}: ERROR - {e}")
            results[name] = -9999.0
        print()

    print("\n=== RESULTS (sorted) ===")
    print(f"  BASELINE (ref): ~472.61")
    for name, score in sorted(results.items(), key=lambda x: x[1], reverse=True):
        print(f"  {name}: {score:.2f}")
