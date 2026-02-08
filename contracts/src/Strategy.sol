// SPDX-License-Identifier: MIT
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

        // Cumulative impact with smooth adaptive decay
        // Carry rate interpolates from 22% (calm) to 60% (turbulent)
        // based on current signal level, replacing binary threshold
        if (trade.timestamp != slots[0]) {
            slots[0] = trade.timestamp;
            uint256 level = slots[1] < WAD / 100 ? slots[1] : WAD / 100;
            uint256 carry = WAD * 22 / 100 + wmul(level, WAD * 35);
            if (carry > WAD * 60 / 100) carry = WAD * 60 / 100;
            slots[1] = wmul(slots[1], carry) + impact;
        } else {
            slots[1] = slots[1] + impact;
        }

        // Slow EMA floor (nearly disabled: 1% alpha)
        slots[2] = wmul(slots[2], WAD * 99 / 100) + wmul(impact, WAD * 1 / 100);

        // Impact volatility: EMA of impact and impact^2 for variance
        uint256 alpha = WAD * 40 / 100;
        slots[3] = wmul(slots[3], WAD - alpha) + wmul(impact, alpha);
        slots[4] = wmul(slots[4], WAD - alpha) + wmul(wmul(impact, impact), alpha);
        uint256 m1sq = wmul(slots[3], slots[3]);
        uint256 variance = slots[4] > m1sq ? slots[4] - m1sq : 0;
        uint256 vol = sqrt(variance * WAD);

        // Signal = max(cumDecay, slowEMA), heavily boosted by volatility
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 boostedSignal = signal + wmul(vol, WAD * 500 / 100);

        // Gentler fee curve (vol signal dominates via 5x boost above)
        uint256 fee = bpsToWad(16) + wmul(boostedSignal, bpsToWad(3800))
                     + wmul(wmul(boostedSignal, boostedSignal), bpsToWad(7000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "VolBoostV2"; }
}
