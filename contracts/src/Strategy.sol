// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";

contract Strategy is AMMStrategyBase {
    // VolBoost-RevSkew-Cubic-Hyst v3 (PressRecov): 502.74 edge at 35 sims
    //
    // Changes from v2 (502.33):
    // - Added signed pressure EMA (slot 7=prevSpot, slot 8=pressure)
    // - When in recovery + persistent one-way flow aligned with deviation,
    //   amplifies skew to 5500 bps mult / 110 bps cap (vs default 5000/100)
    //
    // Slot map:
    // 0: last timestamp
    // 1: cumulative decaying impact
    // 2: slow EMA floor
    // 3: m1 EMA(impact)
    // 4: m2 EMA(impact^2)
    // 5: recovery mode flag (0 = normal, WAD = recovery)
    // 6: spotEMA
    // 7: previous spot price
    // 8: signed pressure EMA (biased at WAD; >WAD = upward, <WAD = downward)

    function afterInitialize(uint256 initialX, uint256 initialY)
        external override returns (uint256, uint256)
    {
        slots[2] = WAD / 200;
        uint256 initSpot = wdiv(initialY, initialX);
        slots[6] = initSpot;
        slots[7] = initSpot;
        slots[8] = WAD;
        return (bpsToWad(30), bpsToWad(30));
    }

    function afterSwap(TradeInfo calldata trade)
        external override returns (uint256 bidFee, uint256 askFee)
    {
        uint256 impact = wdiv(trade.amountY, trade.reserveY);

        // Cumulative impact with conditional decay
        if (trade.timestamp != slots[0]) {
            slots[0] = trade.timestamp;
            uint256 carry = slots[1] < WAD / 200 ? WAD * 33 / 100 : WAD * 45 / 100;
            slots[1] = wmul(slots[1], carry) + impact;
        } else {
            slots[1] = slots[1] + impact;
        }

        // Slow EMA floor
        slots[2] = wmul(slots[2], WAD * 93 / 100) + wmul(impact, WAD * 7 / 100);

        // Impact volatility
        uint256 alpha = WAD / 2;
        slots[3] = wmul(slots[3], WAD - alpha) + wmul(impact, alpha);
        slots[4] = wmul(slots[4], WAD - alpha) + wmul(wmul(impact, impact), alpha);
        uint256 m1sq = wmul(slots[3], slots[3]);
        uint256 variance = slots[4] > m1sq ? slots[4] - m1sq : 0;
        uint256 vol = sqrt(variance * WAD);

        // Signed pressure EMA: tracks persistent directional flow
        uint256 spot = wdiv(trade.reserveY, trade.reserveX);
        uint256 prevSpot = slots[7];
        slots[7] = spot;
        uint256 pA = WAD * 20 / 100;
        slots[8] = wmul(slots[8], WAD - pA) + wmul(spot > prevSpot ? WAD + impact : WAD - impact, pA);
        uint256 absPressure = slots[8] > WAD ? slots[8] - WAD : WAD - slots[8];

        // Signal: max(regime, floor) + vol boost
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 boostedSignal = signal + wmul(vol, WAD * 20 / 100);

        // Cubic fee curve
        uint256 sig2 = wmul(boostedSignal, boostedSignal);
        uint256 sig3 = wmul(sig2, boostedSignal);
        uint256 center = bpsToWad(18)
            + wmul(boostedSignal, bpsToWad(6000))
            + wmul(sig2, bpsToWad(80000))
            + wmul(sig3, bpsToWad(180000));
        center = clampFee(center);

        // Spot EMA (3% alpha)
        slots[6] = wmul(slots[6], WAD * 97 / 100) + wmul(spot, WAD * 3 / 100);
        uint256 spotEma = slots[6];

        // Skew = |spot - spotEMA| / spotEMA
        uint256 diff = spot > spotEma ? (spot - spotEma) : (spotEma - spot);
        uint256 skew = spotEma > 0 ? wdiv(diff, spotEma) : 0;

        // Hysteresis: enter recovery at 0.6% drift, exit at 0.2%
        bool inRecovery = slots[5] > 0;
        if (skew > WAD * 6 / 1000) {
            slots[5] = WAD;
            inRecovery = true;
        } else if (skew < WAD * 2 / 1000) {
            slots[5] = 0;
            inRecovery = false;
        }

        // Pressure alignment: flow direction matches price deviation
        bool pressAligned = (spot > spotEma && slots[8] > WAD)
            || (spot < spotEma && slots[8] < WAD);

        // Recovery: 5000/100 default, 5500/110 when pressure-aligned
        // Normal: 2500/60
        uint256 skewStrength;
        if (inRecovery) {
            uint256 mult = bpsToWad(5000);
            uint256 cap = bpsToWad(100);
            if (pressAligned && absPressure > WAD / 500) {
                mult = bpsToWad(5500);
                cap = bpsToWad(110);
            }
            skewStrength = wmul(skew, mult);
            if (skewStrength > cap) skewStrength = cap;
        } else {
            skewStrength = wmul(skew, bpsToWad(2500));
            if (skewStrength > bpsToWad(60)) skewStrength = bpsToWad(60);
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
        return "VolBoost-RevSkew-Cubic-Hyst-v3";
    }
}
