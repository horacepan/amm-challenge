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
        if (trade.timestamp != slots[0]) {
            slots[0] = trade.timestamp;
            uint256 carry = slots[1] < WAD / 200 ? WAD * 33 / 100 : WAD * 45 / 100;
            slots[1] = wmul(slots[1], carry) + impact;
        } else {
            slots[1] = slots[1] + impact;
        }
        slots[2] = wmul(slots[2], WAD * 93 / 100) + wmul(impact, WAD * (100 - 93) / 100);
        uint256 signal = slots[1] > slots[2] ? slots[1] : slots[2];
        uint256 fee = bpsToWad(20) + wmul(signal, bpsToWad(9500)) + wmul(wmul(signal, signal), bpsToWad(65000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "CondEMA"; }
}
