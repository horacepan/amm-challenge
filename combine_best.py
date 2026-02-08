"""Combine best improvements and test stacking."""
from sweep import score_strategy, STRATEGY_TEMPLATE

N_SIMS = 30

# Confirmed improvements from sweeps (all deterministic, no noise):
# base_fee=18: 473.06 (+0.45)
# linear=9000: 473.03 (+0.42)
# calm=30/turb=45: 472.79 (+0.18)
# calm=33/turb=50: 472.83 (+0.22)
# quad=50000: 472.69 (+0.08)
# quad=40000: 472.68 (+0.07)

def test_combo(name, **overrides):
    base = {
        'calm_carry': 33, 'turb_carry': 45,
        'ema_retain': 93, 'ema_alpha': 7,
        'vol_alpha': 50, 'vol_boost': 20,
        'base_fee': 20, 'linear_coef': 9500, 'quad_coef': 65000,
    }
    base.update(overrides)
    code = STRATEGY_TEMPLATE.format(**base)
    score = score_strategy(code, N_SIMS)
    print(f"  {name}: {score:.2f}  (delta: {score - 472.61:+.2f})")
    return score

print("=== BASELINE ===")
test_combo("original")

print("\n=== STACKING IMPROVEMENTS ===")
# Stack 1: base_fee + linear
test_combo("bf18+lin9000", base_fee=18, linear_coef=9000)

# Stack 2: base_fee + linear + lower quad
test_combo("bf18+lin9000+q50k", base_fee=18, linear_coef=9000, quad_coef=50000)
test_combo("bf18+lin9000+q40k", base_fee=18, linear_coef=9000, quad_coef=40000)

# Stack 3: + carry tuning
test_combo("bf18+lin9000+q50k+c30t45", base_fee=18, linear_coef=9000, quad_coef=50000, calm_carry=30, turb_carry=45)
test_combo("bf18+lin9000+q50k+c33t50", base_fee=18, linear_coef=9000, quad_coef=50000, calm_carry=33, turb_carry=50)

# Stack 4: wider search around these combos
test_combo("bf17+lin9000+q50k", base_fee=17, linear_coef=9000, quad_coef=50000)
test_combo("bf19+lin9000+q50k", base_fee=19, linear_coef=9000, quad_coef=50000)
test_combo("bf18+lin8500+q50k", base_fee=18, linear_coef=8500, quad_coef=50000)
test_combo("bf18+lin9500+q50k", base_fee=18, linear_coef=9500, quad_coef=50000)
test_combo("bf18+lin9000+q45k", base_fee=18, linear_coef=9000, quad_coef=45000)
test_combo("bf18+lin9000+q55k", base_fee=18, linear_coef=9000, quad_coef=55000)

# Fine search around best combo
print("\n=== FINE TUNING ===")
test_combo("bf18+lin8800+q48k", base_fee=18, linear_coef=8800, quad_coef=48000)
test_combo("bf18+lin9200+q48k", base_fee=18, linear_coef=9200, quad_coef=48000)
test_combo("bf18+lin9000+q48k", base_fee=18, linear_coef=9000, quad_coef=48000)
test_combo("bf17+lin9000+q48k", base_fee=17, linear_coef=9000, quad_coef=48000)
test_combo("bf19+lin9000+q48k", base_fee=19, linear_coef=9000, quad_coef=48000)
