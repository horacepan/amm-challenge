// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";

contract Strategy is AMMStrategyBase {
    // Slot map:
    // 0: last timestamp
    // 1: cumulative decaying impact
    // 2: slow EMA floor
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
                carry = WAD * 55 / 100;  // recovery: retain more memory
            } else {
                carry = slots[1] < WAD / 200 ? WAD * 20 / 100 : WAD * 45 / 100;
            }
            slots[1] = wmul(slots[1], carry) + impact;
            slots[7] = impact;  // record first impact of step
            slots[8] = 1;
        } else {
            slots[1] = slots[1] + impact;
            slots[8] = slots[8] + 1;
        }

        // Slow EMA floor (1% alpha)
        slots[2] = wmul(slots[2], WAD * 99 / 100) + wmul(impact, WAD * 1 / 100);

        // Signal: max(cumImpact, floor)
        uint256 s = slots[1] > slots[2] ? slots[1] : slots[2];

        // Cubic fee curve
        uint256 s2 = wmul(s, s);
        uint256 s3 = wmul(s2, s);
        uint256 center = bpsToWad(21)
            + wmul(s, bpsToWad(5000))
            + wmul(s2, bpsToWad(40000))
            + wmul(s3, bpsToWad(100000));
        center = clampFee(center);

        // Harvest discount: reduce fees after 2+ trades if step started with large impact
        if (slots[8] > 1) {  // from 2nd trade onwards
            uint256 discount = wmul(slots[7], bpsToWad(1500));  // 15% of first impact
            center = center > discount ? center - discount : 0;
        }

        // Spot EMA (2% alpha)
        uint256 spot = wdiv(trade.reserveY, trade.reserveX);
        slots[6] = wmul(slots[6], WAD * 98 / 100) + wmul(spot, WAD * 2 / 100);
        uint256 spotEma = slots[6];

        // Skew = |spot - spotEMA| / spotEMA
        uint256 diff = spot > spotEma ? (spot - spotEma) : (spotEma - spot);
        uint256 skew = spotEma > 0 ? wdiv(diff, spotEma) : 0;

        // Hysteresis: enter recovery at 2.5% drift, exit at 0.5%
        bool inRecovery = slots[5] > 0;
        if (skew > WAD * 25 / 1000) {
            slots[5] = WAD;
            inRecovery = true;
        } else if (skew < WAD * 5 / 1000) {
            slots[5] = 0;
            inRecovery = false;
        }

        uint256 skewStrength;
        if (inRecovery) {
            skewStrength = wmul(skew, bpsToWad(5000));
            if (skewStrength > bpsToWad(1000)) skewStrength = bpsToWad(1000);
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
