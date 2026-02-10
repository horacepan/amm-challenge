"""Test tox center terms (properly ordered) + stale direction shift."""
import subprocess
import re

def run_sol(code, sims=35):
    with open("contracts/src/Strategy.sol", "w") as f:
        f.write(code)
    result = subprocess.run(
        ["amm-match", "run", "contracts/src/Strategy.sol", "--simulations", str(sims)],
        capture_output=True, text=True, timeout=300
    )
    output = result.stdout + result.stderr
    match = re.search(r"Edge:\s+([-\d.]+)", output)
    if match:
        return float(match.group(1))
    print(f"  COMPILE ERROR or missing output: {output[-200:]}")
    return None

# Base template with tox computed BEFORE center
BASE = """// SPDX-License-Identifier: MIT
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
                carry = WAD * 60 / 100;
            }} else {{
                carry = slots[1] < WAD / 200 ? WAD * 20 / 100 : WAD * 40 / 100;
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

        // Compute tox BEFORE center
        uint256 tox = pHat > 0 ? wdiv(absDiff(spot, pHat), pHat) : 0;
        if (tox > WAD / 5) tox = WAD / 5;

        uint256 s2 = wmul(s, s);
        uint256 s3 = wmul(s2, s);
        uint256 center = bpsToWad(21)
            + wmul(s, bpsToWad(5000))
            + wmul(s2, bpsToWad(20000))
            + wmul(s3, bpsToWad(100000));
{extra_center}
        center = clampFee(center);

        if (slots[8] > 1) {{
            uint256 discount = wmul(slots[7], bpsToWad(1500));
            center = center > discount ? center - discount : 0;
        }}

        bool inRecovery = slots[5] > 0;
        if (tox > WAD * 10 / 1000) {{
            slots[5] = WAD;
            inRecovery = true;
        }} else if (tox < WAD * 3 / 1000) {{
            slots[5] = 0;
            inRecovery = false;
        }}

        uint256 skewStrength;
        if (inRecovery) {{
            skewStrength = wmul(tox, bpsToWad(6500));
            if (skewStrength > bpsToWad(1000)) skewStrength = bpsToWad(1000);
        }} else {{
            skewStrength = wmul(tox, bpsToWad(6500));
            if (skewStrength > bpsToWad(5000)) skewStrength = bpsToWad(5000);
        }}

{extra_skew}
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

# 1. Verify base
print("=== Verify base ===")
e = run_sol(BASE.format(extra_center="", extra_skew=""))
print(f"  Base: {e}")

# 2. Tox center terms (now properly ordered)
print("\n=== Tox center terms ===")
tests = [
    ("100*tox", "        center = center + wmul(bpsToWad(100), tox);"),
    ("200*tox", "        center = center + wmul(bpsToWad(200), tox);"),
    ("200*tox+8000*tox2", "        center = center + wmul(bpsToWad(200), tox) + wmul(bpsToWad(8000), wmul(tox, tox));"),
    ("sigma*2000", "        center = center + wmul(sigmaHat, bpsToWad(2000));"),
    ("sigma*1000+tox*100", "        center = center + wmul(sigmaHat, bpsToWad(1000)) + wmul(bpsToWad(100), tox);"),
]
for label, code in tests:
    e = run_sol(BASE.format(extra_center=code, extra_skew=""))
    print(f"  {label}: {e}")

# 3. Extra stale-direction shift (on top of skew, like yq's STALE_DIR_COEF)
print("\n=== Stale direction shift ===")
stale_tests = [
    ("stale 3000*tox", """        // Stale direction shift: extra protection on mispricing side
        uint256 staleShift = wmul(bpsToWad(3000), tox);
        uint256 attractShift = wmul(staleShift, WAD * 80 / 100);
        if (spot > pHat) {{
            bidFee = bidFee + staleShift;
            askFee = askFee > attractShift ? askFee - attractShift : 0;
        }} else {{
            askFee = askFee + staleShift;
            bidFee = bidFee > attractShift ? bidFee - attractShift : 0;
        }}"""),
    ("stale 5000*tox", """        uint256 staleShift = wmul(bpsToWad(5000), tox);
        uint256 attractShift = wmul(staleShift, WAD * 80 / 100);
        if (spot > pHat) {{
            bidFee = bidFee + staleShift;
            askFee = askFee > attractShift ? askFee - attractShift : 0;
        }} else {{
            askFee = askFee + staleShift;
            bidFee = bidFee > attractShift ? bidFee - attractShift : 0;
        }}"""),
]
# For stale tests, need to apply AFTER bid/ask computed
# Actually, need different template. Let me use extra_skew to insert code after bid/ask
# No wait, extra_skew is BEFORE the if(spot>pHat). Need to restructure.
# Let me just test directly.

STALE_TEMPLATE = """// SPDX-License-Identifier: MIT
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
                carry = WAD * 60 / 100;
            }} else {{
                carry = slots[1] < WAD / 200 ? WAD * 20 / 100 : WAD * 40 / 100;
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
        uint256 tox = pHat > 0 ? wdiv(absDiff(spot, pHat), pHat) : 0;
        if (tox > WAD / 5) tox = WAD / 5;

        uint256 s2 = wmul(s, s);
        uint256 s3 = wmul(s2, s);
        uint256 center = bpsToWad(21)
            + wmul(s, bpsToWad(5000))
            + wmul(s2, bpsToWad(20000))
            + wmul(s3, bpsToWad(100000));
        center = clampFee(center);

        if (slots[8] > 1) {{
            uint256 discount = wmul(slots[7], bpsToWad(1500));
            center = center > discount ? center - discount : 0;
        }}

        bool inRecovery = slots[5] > 0;
        if (tox > WAD * 10 / 1000) {{
            slots[5] = WAD;
            inRecovery = true;
        }} else if (tox < WAD * 3 / 1000) {{
            slots[5] = 0;
            inRecovery = false;
        }}

        uint256 skewStrength;
        if (inRecovery) {{
            skewStrength = wmul(tox, bpsToWad(6500));
            if (skewStrength > bpsToWad(1000)) skewStrength = bpsToWad(1000);
        }} else {{
            skewStrength = wmul(tox, bpsToWad(6500));
            if (skewStrength > bpsToWad(5000)) skewStrength = bpsToWad(5000);
        }}

        if (spot > pHat) {{
            bidFee = clampFee(center + skewStrength);
            askFee = clampFee(center > skewStrength ? center - skewStrength : 0);
        }} else {{
            bidFee = clampFee(center > skewStrength ? center - skewStrength : 0);
            askFee = clampFee(center + skewStrength);
        }}

        // Stale direction shift
        uint256 staleShift = wmul(bpsToWad({stale_coef}), tox);
        uint256 attractFrac = WAD * {attract_pct} / 100;
        if (spot > pHat) {{
            bidFee = clampFee(bidFee + staleShift);
            uint256 attract = wmul(staleShift, attractFrac);
            askFee = askFee > attract ? askFee - attract : 0;
        }} else {{
            askFee = clampFee(askFee + staleShift);
            uint256 attract = wmul(staleShift, attractFrac);
            bidFee = bidFee > attract ? bidFee - attract : 0;
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

print("\n=== Stale direction shift ===")
for coef in [1000, 2000, 3000, 5000]:
    for attract in [50, 80, 100, 120]:
        e = run_sol(STALE_TEMPLATE.format(stale_coef=coef, attract_pct=attract))
        print(f"  stale={coef}, attract={attract}%: {e}")
