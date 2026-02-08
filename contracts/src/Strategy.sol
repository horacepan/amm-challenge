// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";
contract Strategy is AMMStrategyBase {
    // slots[0] = last timestamp (step detection)
    // slots[1] = cumulative decaying impact (state across trades/steps)
    function afterInitialize(uint256, uint256) external override returns (uint256, uint256) {
        return (bpsToWad(30), bpsToWad(30));
    }
    function afterSwap(TradeInfo calldata trade) external override returns (uint256, uint256) {
        uint256 impact = wdiv(trade.amountY, trade.reserveY);

        // Accumulate impact within step; decay 60% across steps
        if (trade.timestamp != slots[0]) {
            slots[0] = trade.timestamp;
            slots[1] = wmul(slots[1], WAD * 40 / 100) + impact;
        } else {
            slots[1] = slots[1] + impact;
        }

        uint256 cumImpact = slots[1];
        uint256 fee = bpsToWad(20) + wmul(cumImpact, bpsToWad(9500)) + wmul(wmul(cumImpact, cumImpact), bpsToWad(65000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "CumDecay"; }
}
