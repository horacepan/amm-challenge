"""Targeted parameter sweep focusing on fee curve coefficients."""
import sys
from sweep import score_strategy, STRATEGY_TEMPLATE

N_SIMS = 30

def test_params(params, label=""):
    """Test a parameter set and return score."""
    code = STRATEGY_TEMPLATE.format(**params)
    score = score_strategy(code, N_SIMS)
    return score

def main():
    base = {
        'calm_carry': 33, 'turb_carry': 45,
        'ema_retain': 93, 'ema_alpha': 7,
        'vol_alpha': 50, 'vol_boost': 20,
        'base_fee': 20, 'linear_coef': 9500, 'quad_coef': 65000,
    }

    # First, sweep linear and quad coefficients more finely
    # These are the explicitly un-tuned parameters
    print("=== ROUND 1: Linear coefficient sweep ===")
    for lc in [6000, 7000, 8000, 9000, 9500, 10000, 11000, 12000, 14000]:
        p = dict(base); p['linear_coef'] = lc
        s = test_params(p)
        print(f"  linear={lc}: {s:.2f}")

    print("\n=== ROUND 2: Quad coefficient sweep ===")
    for qc in [30000, 40000, 50000, 55000, 60000, 65000, 70000, 80000, 100000, 120000]:
        p = dict(base); p['quad_coef'] = qc
        s = test_params(p)
        print(f"  quad={qc}: {s:.2f}")

    print("\n=== ROUND 3: Base fee sweep ===")
    for bf in [5, 10, 15, 18, 20, 22, 25, 28, 30, 35]:
        p = dict(base); p['base_fee'] = bf
        s = test_params(p)
        print(f"  base_fee={bf}: {s:.2f}")

    print("\n=== ROUND 4: Vol boost sweep ===")
    for vb in [5, 10, 15, 20, 25, 30, 35, 40, 50, 60]:
        p = dict(base); p['vol_boost'] = vb
        s = test_params(p)
        print(f"  vol_boost={vb}: {s:.2f}")

    print("\n=== ROUND 5: Vol alpha sweep ===")
    for va in [20, 30, 40, 50, 60, 70, 80]:
        p = dict(base); p['vol_alpha'] = va
        s = test_params(p)
        print(f"  vol_alpha={va}: {s:.2f}")

    # Carry rates
    print("\n=== ROUND 6: Carry rates ===")
    for cc, tc in [(25, 40), (28, 42), (30, 45), (33, 45), (33, 50), (35, 50), (35, 55), (38, 55), (40, 60)]:
        p = dict(base); p['calm_carry'] = cc; p['turb_carry'] = tc
        s = test_params(p)
        print(f"  calm={cc}, turb={tc}: {s:.2f}")

    # EMA params
    print("\n=== ROUND 7: Slow EMA ===")
    for er, ea in [(90, 10), (91, 9), (92, 8), (93, 7), (94, 6), (95, 5), (96, 4), (97, 3)]:
        p = dict(base); p['ema_retain'] = er; p['ema_alpha'] = ea
        s = test_params(p)
        print(f"  ema_retain={er}, ema_alpha={ea}: {s:.2f}")


if __name__ == "__main__":
    main()
