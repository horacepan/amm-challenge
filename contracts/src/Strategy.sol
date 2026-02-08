// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";

contract Strategy is AMMStrategyBase {
    // Slot map:
    // 0: last timestamp
    // 1: cumulative decaying impact
    // 2: slow EMA floor
    // 3: EMA(impact)
    // 4: EMA(impact^2)
    // 5: recovery mode flag (0 = normal, WAD = recovery)
    // 6: spotEMA
    // 7: first impact of current step
    // 8: trade count in current step

    function afterInitialize(uint256 initialX, uint256 initialY)
        external override returns (uint256, uint256)
    {
        slots[2] = WAD / 200;
        slots[6] = wdiv(initialY, initialX);
        return (bpsToWad(30), bpsToWad(30));
    }

    function afterSwap(TradeInfo calldata trade)
        external override returns (uint256 bidFee, uint256 askFee)
    {
        uint256 impact = wdiv(trade.amountY, trade.reserveY);

        // Cumulative impact with regime-aware decay
        if (trade.timestamp != slots[0]) {
            slots[0] = trade.timestamp;
            uint256 carry;
            if (slots[5] > 0) {
                carry = WAD * 50 / 100;  // recovery: retain more memory
            } else {
                carry = slots[1] < WAD / 200 ? WAD * 33 / 100 : WAD * 45 / 100;
            }
            slots[1] = wmul(slots[1], carry) + impact;
            slots[7] = impact;  // record first impact of step
            slots[8] = 1;
        } else {
            slots[1] = slots[1] + impact;
            slots[8] = slots[8] + 1;
        }

        // Slow EMA floor (7% alpha)
        slots[2] = wmul(slots[2], WAD * 93 / 100) + wmul(impact, WAD * 7 / 100);

        // Impact volatility
        uint256 alpha = WAD * 50 / 100;
        slots[3] = wmul(slots[3], WAD - alpha) + wmul(impact, alpha);
        slots[4] = wmul(slots[4], WAD - alpha) + wmul(wmul(impact, impact), alpha);
        uint256 m1sq = wmul(slots[3], slots[3]);
        uint256 variance = slots[4] > m1sq ? slots[4] - m1sq : 0;
        uint256 vol = sqrt(variance * WAD);

        // Signal: max(cumImpact, floor) + vol boost
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 s = signal + wmul(vol, WAD * 20 / 100);

        // Cubic fee curve
        uint256 s2 = wmul(s, s);
        uint256 s3 = wmul(s2, s);
        uint256 center = bpsToWad(19)
            + wmul(s, bpsToWad(6000))
            + wmul(s2, bpsToWad(80000))
            + wmul(s3, bpsToWad(180000));
        center = clampFee(center);

        // Harvest discount: reduce fees after 2+ trades if step started with large impact
        if (slots[8] > 1) {  // from 2nd trade onwards
            uint256 discount = wmul(slots[7], bpsToWad(3500));  // 35% of first impact
            center = center > discount ? center - discount : 0;
        }

        // Spot EMA (3% alpha)
        uint256 spot = wdiv(trade.reserveY, trade.reserveX);
        slots[6] = wmul(slots[6], WAD * 97 / 100) + wmul(spot, WAD * 3 / 100);
        uint256 spotEma = slots[6];

        // Skew = |spot - spotEMA| / spotEMA
        uint256 diff = spot > spotEma ? (spot - spotEma) : (spotEma - spot);
        uint256 skew = spotEma > 0 ? wdiv(diff, spotEma) : 0;

        // Hysteresis: enter recovery at 0.7% drift, exit at 0.3%
        bool inRecovery = slots[5] > 0;
        if (skew > WAD * 7 / 1000) {
            slots[5] = WAD;
            inRecovery = true;
        } else if (skew < WAD * 3 / 1000) {
            slots[5] = 0;
            inRecovery = false;
        }

        uint256 skewStrength;
        if (inRecovery) {
            skewStrength = wmul(skew, bpsToWad(4500));
            if (skewStrength > bpsToWad(160)) skewStrength = bpsToWad(160);
        } else {
            skewStrength = wmul(skew, bpsToWad(4000));
            if (skewStrength > bpsToWad(90)) skewStrength = bpsToWad(90);
        }

        // Reversed skew: attract rebalancing flow
        if (spot > spotEma) {
            bidFee = clampFee(center + skewStrength);
            askFee = clampFee(center > skewStrength ? center - skewStrength : 0);
        } else {
            bidFee = clampFee(center > skewStrength ? center - skewStrength : 0);
            askFee = clampFee(center + skewStrength);
        }

        return (bidFee, askFee);
    }

    function getName() external pure override returns (string memory) {
        return "CondCum-Cubic-RevSkew-Hyst";
    }
}
