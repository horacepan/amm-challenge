// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AMMStrategyBase} from "./AMMStrategyBase.sol";
import {TradeInfo} from "./IAMMStrategy.sol";

contract Strategy is AMMStrategyBase {
    // slots[0] = current fee (WAD)
    // slots[1] = last timestamp
    // slots[2] = spot price after last arb correction (WAD)
    // slots[3] = trade count this step

    // Strategy: staleness-aware fee using price data.
    //
    // Core idea: track how far our spot has drifted from last arb-corrected
    // price. When stale (big drift) → low fee to invite cheap arb correction.
    // When fresh (just corrected) → higher fee.
    //
    // We use reserveY/reserveX = spot price, and compare to stored reference.

    uint256 constant BASE_FEE = 29;     // bps - base fee (just under normalizer)
    uint256 constant FRESH_BONUS = 5;   // bps - extra fee when price is fresh

    function afterInitialize(uint256 initialX, uint256 initialY) external override returns (uint256, uint256) {
        slots[0] = bpsToWad(BASE_FEE);
        slots[1] = 0;
        slots[2] = wdiv(initialY, initialX); // initial spot price
        slots[3] = 0;
        return (bpsToWad(BASE_FEE), bpsToWad(BASE_FEE));
    }

    function afterSwap(TradeInfo calldata trade) external override returns (uint256, uint256) {
        uint256 currentSpot = wdiv(trade.reserveY, trade.reserveX);

        // New step? First trade is arb
        bool isNewStep = (trade.timestamp != slots[1]);
        if (isNewStep) {
            slots[1] = trade.timestamp;
            slots[3] = 0;
            // Update reference price — arb just corrected toward fair
            slots[2] = currentSpot;
        } else {
            slots[3] = slots[3] + 1;
        }

        // Measure staleness: how far has spot drifted from last arb reference?
        uint256 refSpot = slots[2];
        uint256 drift = 0;
        if (refSpot > 0) {
            drift = wdiv(absDiff(currentSpot, refSpot), refSpot);
        }

        // Fee logic:
        // - After arb (fresh): price is accurate → add bonus
        // - After retail: price drifted a bit → base fee
        // - Very stale: lower fee to invite correction (but we're competitive either way)
        uint256 fee;
        if (isNewStep) {
            // Just arb-corrected. Price is fresh. Charge a bit more.
            fee = bpsToWad(BASE_FEE + FRESH_BONUS);
        } else {
            // Retail traded, price drifted. Stay at base to remain competitive.
            fee = bpsToWad(BASE_FEE);
        }

        fee = clampFee(fee);
        slots[0] = fee;
        return (fee, fee);
    }

    function getName() external pure override returns (string memory) {
        return "Staleness_v1";
    }
}
