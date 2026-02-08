"""Test multiple structural strategy variants."""
import sys
from sweep import score_strategy

# 1. BASELINE (current VolBoost)
BASELINE = """// SPDX-License-Identifier: MIT
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
    function getName() external pure override returns (string memory) { return "Baseline"; }
}
"""

# 2. TRADE COUNT TRACKING - Track number of trades per step as activity signal
TRADE_COUNT = """// SPDX-License-Identifier: MIT
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

        // Track trade count per step (slot 5) and EMA of trade count (slot 6)
        if (trade.timestamp != slots[0]) {
            // New step: update trade count EMA from last step's count
            if (slots[0] > 0) {
                // EMA of trade count (activity signal)
                slots[6] = wmul(slots[6], WAD * 80 / 100) + wmul(slots[5] * WAD, WAD * 20 / 100);
            }
            slots[5] = WAD; // reset counter to 1
            slots[0] = trade.timestamp;
            uint256 carry = slots[1] < WAD / 200 ? WAD * 33 / 100 : WAD * 45 / 100;
            slots[1] = wmul(slots[1], carry) + impact;
        } else {
            slots[5] = slots[5] + WAD; // increment counter
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

        // Add small activity boost based on trade count EMA
        // More trades per step = more active market = slightly higher fees
        uint256 activityBoost = wmul(slots[6], WAD * 2 / 100);  // 2% of activity EMA
        boostedSignal = boostedSignal + activityBoost;

        uint256 fee = bpsToWad(20) + wmul(boostedSignal, bpsToWad(9500)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(65000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "TradeCount"; }
}
"""

# 3. MAX IMPACT MEMORY - Track the max impact seen in recent history
MAX_IMPACT = """// SPDX-License-Identifier: MIT
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
            // Decay the peak impact tracker across steps
            slots[5] = wmul(slots[5], WAD * 85 / 100);
        } else {
            slots[1] = slots[1] + impact;
        }

        // Track max impact (decaying)
        if (impact > slots[5]) {
            slots[5] = impact;
        }

        slots[2] = wmul(slots[2], WAD * 93 / 100) + wmul(impact, WAD * 7 / 100);
        uint256 alpha = WAD * 50 / 100;
        slots[3] = wmul(slots[3], WAD - alpha) + wmul(impact, alpha);
        slots[4] = wmul(slots[4], WAD - alpha) + wmul(wmul(impact, impact), alpha);
        uint256 m1sq = wmul(slots[3], slots[3]);
        uint256 variance = slots[4] > m1sq ? slots[4] - m1sq : 0;
        uint256 vol = sqrt(variance * WAD);

        // Use max(cumDecay, slowEMA, peakImpact*factor) as signal
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 peakSignal = wmul(slots[5], WAD * 50 / 100); // 50% of peak
        if (peakSignal > signal) signal = peakSignal;

        uint256 boostedSignal = signal + wmul(vol, WAD * 20 / 100);

        uint256 fee = bpsToWad(20) + wmul(boostedSignal, bpsToWad(9500)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(65000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "MaxImpact"; }
}
"""

# 4. CUBIC FEE CURVE - Add cubic term alongside existing quadratic
CUBIC_FEE = """// SPDX-License-Identifier: MIT
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
        uint256 s2 = wmul(boostedSignal, boostedSignal);
        uint256 s3 = wmul(s2, boostedSignal);
        uint256 fee = bpsToWad(20) + wmul(boostedSignal, bpsToWad(8000)) + wmul(s2, bpsToWad(50000)) + wmul(s3, bpsToWad(200000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "CubicFee"; }
}
"""

# 5. ASYMMETRIC FEES - Different bid/ask based on recent direction
ASYMMETRIC = """// SPDX-License-Identifier: MIT
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

        // Track directional EMA: isBuy=true -> AMM bought X -> bias = high
        // Use a directional bias to slightly widen/narrow the active side
        uint256 dirAlpha = WAD * 30 / 100;
        if (trade.isBuy) {
            // AMM bought X (price was high), arbs sold X to us
            // Raise bid fee slightly (discourage more sells to us)
            slots[5] = wmul(slots[5], WAD - dirAlpha) + wmul(impact, dirAlpha);
            slots[6] = wmul(slots[6], WAD - dirAlpha);
        } else {
            // AMM sold X (price was low), arbs bought X from us
            // Raise ask fee slightly (discourage more buys from us)
            slots[6] = wmul(slots[6], WAD - dirAlpha) + wmul(impact, dirAlpha);
            slots[5] = wmul(slots[5], WAD - dirAlpha);
        }

        uint256 bidBoost = wmul(slots[5], bpsToWad(3000));
        uint256 askBoost = wmul(slots[6], bpsToWad(3000));

        uint256 bidFee = fee + bidBoost;
        uint256 askFee = fee + askBoost;

        return (clampFee(bidFee), clampFee(askFee));
    }
    function getName() external pure override returns (string memory) { return "Asymmetric"; }
}
"""

# 6. SMOOTHER DECAY - Continuous carry rate instead of binary threshold
SMOOTH_DECAY = """// SPDX-License-Identifier: MIT
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
            // Smooth carry: interpolate between 30% and 50% based on signal level
            // carry = 30% + min(slots[1], WAD/100) * 20 / (WAD/100)
            // = 30% + min(slots[1], WAD/100) * 2000
            uint256 level = slots[1] < WAD / 100 ? slots[1] : WAD / 100;
            uint256 carry = WAD * 30 / 100 + wmul(level, WAD * 20);
            if (carry > WAD * 50 / 100) carry = WAD * 50 / 100;
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
    function getName() external pure override returns (string memory) { return "SmoothDecay"; }
}
"""

# 7. VOL-ADAPTIVE CARRY - Use vol to modulate carry rate
VOL_CARRY = """// SPDX-License-Identifier: MIT
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

        // Compute vol first so we can use it for carry
        uint256 alpha = WAD * 50 / 100;
        slots[3] = wmul(slots[3], WAD - alpha) + wmul(impact, alpha);
        slots[4] = wmul(slots[4], WAD - alpha) + wmul(wmul(impact, impact), alpha);
        uint256 m1sq = wmul(slots[3], slots[3]);
        uint256 variance = slots[4] > m1sq ? slots[4] - m1sq : 0;
        uint256 vol = sqrt(variance * WAD);

        if (trade.timestamp != slots[0]) {
            slots[0] = trade.timestamp;
            // Use vol to modulate carry: high vol -> higher carry (persist fees)
            // Base carry 33%, boost up to 55% based on vol
            uint256 volCarryBoost = wmul(vol, WAD * 400 / 100); // Scale vol up
            if (volCarryBoost > WAD * 22 / 100) volCarryBoost = WAD * 22 / 100;
            uint256 carry = WAD * 33 / 100 + volCarryBoost;
            slots[1] = wmul(slots[1], carry) + impact;
        } else {
            slots[1] = slots[1] + impact;
        }
        slots[2] = wmul(slots[2], WAD * 93 / 100) + wmul(impact, WAD * 7 / 100);
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 boostedSignal = signal + wmul(vol, WAD * 20 / 100);
        uint256 fee = bpsToWad(20) + wmul(boostedSignal, bpsToWad(9500)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(65000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "VolCarry"; }
}
"""

# 8. DOUBLE DECAY - Two cumulative impact trackers at different timescales
DOUBLE_DECAY = """// SPDX-License-Identifier: MIT
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
            // Fast decay tracker (existing)
            uint256 carry = slots[1] < WAD / 200 ? WAD * 33 / 100 : WAD * 45 / 100;
            slots[1] = wmul(slots[1], carry) + impact;
            // Slow decay tracker (slot 5) - higher persistence
            slots[5] = wmul(slots[5], WAD * 70 / 100) + impact;
        } else {
            slots[1] = slots[1] + impact;
            slots[5] = slots[5] + impact;
        }
        slots[2] = wmul(slots[2], WAD * 93 / 100) + wmul(impact, WAD * 7 / 100);
        uint256 alpha = WAD * 50 / 100;
        slots[3] = wmul(slots[3], WAD - alpha) + wmul(impact, alpha);
        slots[4] = wmul(slots[4], WAD - alpha) + wmul(wmul(impact, impact), alpha);
        uint256 m1sq = wmul(slots[3], slots[3]);
        uint256 variance = slots[4] > m1sq ? slots[4] - m1sq : 0;
        uint256 vol = sqrt(variance * WAD);

        // Blend fast and slow signals: use max of all three
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 slowSignal = wmul(slots[5], WAD * 60 / 100); // Weight slow tracker
        if (slowSignal > signal) signal = slowSignal;

        uint256 boostedSignal = signal + wmul(vol, WAD * 20 / 100);
        uint256 fee = bpsToWad(20) + wmul(boostedSignal, bpsToWad(9500)) + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(65000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "DoubleDecay"; }
}
"""


strategies = {
    "BASELINE": BASELINE,
    "TRADE_COUNT": TRADE_COUNT,
    "MAX_IMPACT": MAX_IMPACT,
    "CUBIC_FEE": CUBIC_FEE,
    "ASYMMETRIC": ASYMMETRIC,
    "SMOOTH_DECAY": SMOOTH_DECAY,
    "VOL_CARRY": VOL_CARRY,
    "DOUBLE_DECAY": DOUBLE_DECAY,
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
    for name, score in sorted(results.items(), key=lambda x: x[1], reverse=True):
        marker = " (baseline)" if name == "BASELINE" else ""
        print(f"  {name}: {score:.2f}{marker}")
