// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";
contract Strategy is AMMStrategyBase {
    function afterInitialize(uint256, uint256) external override returns (uint256, uint256) {
        return (bpsToWad(30), bpsToWad(30));
    }
    function afterSwap(TradeInfo calldata trade) external override returns (uint256, uint256) {
        uint256 impact = wdiv(trade.amountY, trade.reserveY);
        uint256 fee = bpsToWad(30) + wmul(impact, bpsToWad(8200)) + wmul(wmul(impact, impact), bpsToWad(43000));
        return (clampFee(fee), clampFee(fee));
    }
    function getName() external pure override returns (string memory) { return "SizeAdapt"; }
}
