"""Fine-grained sweep around best tox-skew params."""
import subprocess
import re

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
            + wmul(s, bpsToWad({lin_coef}))
            + wmul(s2, bpsToWad({quad_coef}))
            + wmul(s3, bpsToWad({cubic_coef}));
        center = clampFee(center);

        if (slots[8] > 1) {{
            uint256 discount = wmul(slots[7], bpsToWad(1500));
            center = center > discount ? center - discount : 0;
        }}

        uint256 tox = pHat > 0 ? wdiv(absDiff(spot, pHat), pHat) : 0;
        if (tox > WAD / 5) tox = WAD / 5;

        uint256 skewStrength = wmul(tox, bpsToWad({skew_mult}));
        if (skewStrength > bpsToWad({skew_cap})) skewStrength = bpsToWad({skew_cap});

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
    print(f"  No edge found")
    return None

# No hysteresis - single regime
base = dict(base_fee=21, lin_coef=5000, quad_coef=40000, cubic_coef=100000,
            skew_mult=6000, skew_cap=5000)

# Verify no-hysteresis base (simpler is better)
print("=== No hysteresis, single regime ===")
e = run_test(base)
print(f"  skew_mult=6000, cap=5000: {e}")

# Fine-sweep skew_mult
print("\n=== Fine sweep skew_mult ===")
for mult in [4500, 5000, 5500, 6000, 6500, 7000, 7500]:
    p = {**base, 'skew_mult': mult}
    e = run_test(p)
    print(f"  mult={mult}: {e}")

# Sweep cap
print("\n=== Sweep cap with mult=6000 ===")
for cap in [200, 400, 600, 800, 1000, 2000, 5000]:
    p = {**base, 'skew_cap': cap}
    e = run_test(p)
    print(f"  cap={cap}: {e}")

# With best mult, sweep base fee
print("\n=== Sweep base fee ===")
for fee in [17, 19, 21, 23, 25]:
    p = {**base, 'base_fee': fee}
    e = run_test(p)
    print(f"  base_fee={fee}: {e}")

# Sweep cubic coefficients with new skew
print("\n=== Sweep linear coef ===")
for lin in [3000, 4000, 5000, 6000, 7000]:
    p = {**base, 'lin_coef': lin}
    e = run_test(p)
    print(f"  lin={lin}: {e}")

print("\n=== Sweep quadratic coef ===")
for quad in [20000, 30000, 40000, 50000, 60000]:
    p = {**base, 'quad_coef': quad}
    e = run_test(p)
    print(f"  quad={quad}: {e}")

print("\n=== Sweep cubic coef ===")
for cub in [50000, 80000, 100000, 120000, 150000]:
    p = {**base, 'cubic_coef': cub}
    e = run_test(p)
    print(f"  cubic={cub}: {e}")
