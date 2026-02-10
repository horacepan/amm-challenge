"""Sweep tox-skew parameters."""
import subprocess
import re
import sys

TEMPLATE = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {{AMMStrategyBase}} from "./AMMStrategyBase.sol";
import {{TradeInfo}} from "./IAMMStrategy.sol";

contract Strategy is AMMStrategyBase {{
    function afterInitialize(uint256 initialX, uint256 initialY)
        external override returns (uint256, uint256)
    {{
        slots[2] = WAD / 200;
        uint256 spot = wdiv(initialY, initialX);
        slots[3] = spot;
        slots[4] = WAD / 1000;
        uint256 initFee = bpsToWad(30);
        slots[9] = initFee;
        slots[10] = initFee;
        return (initFee, initFee);
    }}

    function afterSwap(TradeInfo calldata trade)
        external override returns (uint256 bidFee, uint256 askFee)
    {{
        uint256 impact = wdiv(trade.amountY, trade.reserveY);
        uint256 pHat = slots[3];
        uint256 sigmaHat = slots[4];

        if (trade.timestamp != slots[0]) {{
            slots[0] = trade.timestamp;
            uint256 carry;
            if (slots[5] > 0) {{
                carry = WAD * 55 / 100;
            }} else {{
                carry = slots[1] < WAD / 200 ? WAD * 20 / 100 : WAD * 45 / 100;
            }}
            slots[1] = wmul(slots[1], carry) + impact;
            slots[7] = impact;
            slots[8] = 1;
        }} else {{
            slots[1] = slots[1] + impact;
            slots[8] = slots[8] + 1;
        }}

        slots[2] = wmul(slots[2], WAD * 99 / 100) + wmul(impact, WAD * 1 / 100);

        uint256 spot = wdiv(trade.reserveY, trade.reserveX);
        bool firstInStep = slots[8] == 1;
        {{
            uint256 feeUsed = trade.isBuy ? slots[9] : slots[10];
            uint256 gamma = feeUsed < WAD ? WAD - feeUsed : 0;
            uint256 pImplied;
            if (gamma == 0) {{
                pImplied = spot;
            }} else {{
                pImplied = trade.isBuy ? wmul(spot, gamma) : wdiv(spot, gamma);
            }}
            uint256 ret = pHat > 0 ? wdiv(absDiff(pImplied, pHat), pHat) : 0;
            uint256 adaptiveGate = wmul(sigmaHat, 10 * WAD);
            if (adaptiveGate < WAD * 3 / 100) adaptiveGate = WAD * 3 / 100;
            uint256 pAlpha = firstInStep ? WAD * 26 / 100 : WAD * 5 / 100;
            if (ret <= adaptiveGate) {{
                pHat = wmul(pHat, WAD - pAlpha) + wmul(pImplied, pAlpha);
            }}
            if (firstInStep) {{
                uint256 retCapped = ret > WAD / 10 ? WAD / 10 : ret;
                sigmaHat = wmul(sigmaHat, WAD * 824 / 1000) + wmul(retCapped, WAD * 176 / 1000);
            }}
        }}
        slots[3] = pHat;
        slots[4] = sigmaHat;

        uint256 s = slots[1] > slots[2] ? slots[1] : slots[2];

        uint256 s2 = wmul(s, s);
        uint256 s3 = wmul(s2, s);
        uint256 center = bpsToWad({base_fee})
            + wmul(s, bpsToWad(5000))
            + wmul(s2, bpsToWad(40000))
            + wmul(s3, bpsToWad(100000));
        center = clampFee(center);

        if (slots[8] > 1) {{
            uint256 discount = wmul(slots[7], bpsToWad(1500));
            center = center > discount ? center - discount : 0;
        }}

        uint256 tox = pHat > 0 ? wdiv(absDiff(spot, pHat), pHat) : 0;
        if (tox > WAD / 5) tox = WAD / 5;

        bool inRecovery = slots[5] > 0;
        if (tox > WAD * {entry_pct} / 1000) {{
            slots[5] = WAD;
            inRecovery = true;
        }} else if (tox < WAD * {exit_pct} / 1000) {{
            slots[5] = 0;
            inRecovery = false;
        }}

        uint256 skewStrength;
        if (inRecovery) {{
            skewStrength = wmul(tox, bpsToWad({rec_mult}));
            if (skewStrength > bpsToWad({rec_cap})) skewStrength = bpsToWad({rec_cap});
        }} else {{
            skewStrength = wmul(tox, bpsToWad({norm_mult}));
            if (skewStrength > bpsToWad({norm_cap})) skewStrength = bpsToWad({norm_cap});
        }}

        if (spot > pHat) {{
            bidFee = clampFee(center + skewStrength);
            askFee = clampFee(center > skewStrength ? center - skewStrength : 0);
        }} else {{
            bidFee = clampFee(center > skewStrength ? center - skewStrength : 0);
            askFee = clampFee(center + skewStrength);
        }}

        slots[9] = bidFee;
        slots[10] = askFee;
        return (bidFee, askFee);
    }}

    function getName() external pure override returns (string memory) {{
        return "Sweep";
    }}
}}
"""

def run_test(params, sims=35):
    sol = TEMPLATE.format(**params)
    with open("contracts/src/Strategy.sol", "w") as f:
        f.write(sol)
    result = subprocess.run(
        ["amm-match", "run", "contracts/src/Strategy.sol", "--simulations", str(sims)],
        capture_output=True, text=True, timeout=300
    )
    output = result.stdout + result.stderr
    match = re.search(r"Edge:\s+([-\d.]+)", output)
    if match:
        return float(match.group(1))
    print(f"  No edge found in output: {output[-200:]}")
    return None

# Base params (the 518.77 variant)
base = dict(base_fee=21, entry_pct=25, exit_pct=5, rec_mult=5000, rec_cap=1000, norm_mult=4000, norm_cap=90)

# Verify base
print("=== Verifying base ===")
e = run_test(base)
print(f"  Base: {e}")

# Sweep hysteresis entry threshold
print("\n=== Sweep hysteresis entry (tox > X/1000) ===")
for entry in [15, 20, 25, 30, 35, 40]:
    p = {**base, 'entry_pct': entry}
    e = run_test(p)
    print(f"  entry={entry}/1000 ({entry/10:.1f}%): {e}")

# Sweep hysteresis exit threshold
print("\n=== Sweep hysteresis exit (tox < X/1000) ===")
for exit_val in [2, 3, 5, 7, 10]:
    p = {**base, 'exit_pct': exit_val}
    e = run_test(p)
    print(f"  exit={exit_val}/1000 ({exit_val/10:.1f}%): {e}")

# Sweep recovery multiplier
print("\n=== Sweep recovery multiplier ===")
for mult in [3000, 4000, 5000, 6000, 7000]:
    p = {**base, 'rec_mult': mult}
    e = run_test(p)
    print(f"  rec_mult={mult}: {e}")

# Sweep normal multiplier
print("\n=== Sweep normal multiplier ===")
for mult in [2000, 3000, 4000, 5000, 6000]:
    p = {**base, 'norm_mult': mult}
    e = run_test(p)
    print(f"  norm_mult={mult}: {e}")

# Sweep normal cap
print("\n=== Sweep normal cap (bps) ===")
for cap in [50, 70, 90, 120, 150, 200]:
    p = {**base, 'norm_cap': cap}
    e = run_test(p)
    print(f"  norm_cap={cap}: {e}")

# Sweep base fee
print("\n=== Sweep base fee ===")
for fee in [15, 18, 21, 24, 27]:
    p = {**base, 'base_fee': fee}
    e = run_test(p)
    print(f"  base_fee={fee}: {e}")
