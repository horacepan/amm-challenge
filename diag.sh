#!/bin/bash
# Run 100 sims diagnostics in 4 batches, aggregate with Python
SOL=${1:-contracts/src/Strategy.sol}
LABEL=${2:-Strategy}
TMPDIR=$(mktemp -d)

for start in 0 25 50 75; do
    python diag_batch.py "$SOL" $start 25 > "$TMPDIR/batch_${start}.json" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "FAILED at batch starting seed $start" >&2
        exit 1
    fi
done

python3 -c "
import json, sys, numpy as np

all_stats = []
for start in [0, 25, 50, 75]:
    with open('$TMPDIR/batch_{}.json'.format(start)) as f:
        all_stats.extend(json.load(f))

n = len(all_stats)
def arr(key): return np.array([s[key] for s in all_stats])

edge = arr('edge'); norm_edge = arr('norm_edge')
arb_e = arr('arb_edge'); norm_arb_e = arr('norm_arb_edge')
ret_e = arr('retail_edge'); norm_ret_e = arr('norm_retail_edge')
arb_v = arr('arb_vol'); norm_arb_v = arr('norm_arb_vol')
ret_v = arr('retail_vol'); norm_ret_v = arr('norm_retail_vol')
bid = arr('avg_bid'); ask = arr('avg_ask')
nb = arr('norm_avg_bid'); na = arr('norm_avg_ask')
pnl = arr('pnl'); norm_pnl = arr('norm_pnl')

wins = np.sum(edge > norm_edge)
ret_share = ret_v / (ret_v + norm_ret_v)
arb_share = arb_v / (arb_v + norm_arb_v)
mid = (bid + ask) / 2
nmid = (nb + na) / 2

print()
print('=' * 65)
print(f'  $LABEL  ({n} sims)')
print('=' * 65)
print(f'  Edge:          {edge.mean():>8.2f}  (normalizer: {norm_edge.mean():.2f})')
print(f'  Arb edge:      {arb_e.mean():>8.2f}  (normalizer: {norm_arb_e.mean():.2f})')
print(f'  Retail edge:   {ret_e.mean():>8.2f}  (normalizer: {norm_ret_e.mean():.2f})')
print(f'  Edge std:      {edge.std():>8.2f}  (normalizer: {norm_edge.std():.2f})')
print(f'  Win rate:      {wins:>5d}/{n}')
print(f'  PnL:           {pnl.mean():>8.2f}  (normalizer: {norm_pnl.mean():.2f})')
print()
print(f'  Retail vol:    {ret_v.mean():>8.0f}  (normalizer: {norm_ret_v.mean():.0f})')
print(f'  Retail share:  {ret_share.mean()*100:>7.2f}%')
print(f'  Arb vol:       {arb_v.mean():>8.0f}  (normalizer: {norm_arb_v.mean():.0f})')
print(f'  Arb share:     {arb_share.mean()*100:>7.2f}%')
print()
print(f'  Avg bid fee:   {bid.mean()*1e4:>7.1f} bps  (normalizer: {nb.mean()*1e4:.1f} bps)')
print(f'  Avg ask fee:   {ask.mean()*1e4:>7.1f} bps  (normalizer: {na.mean()*1e4:.1f} bps)')
print(f'  Avg mid fee:   {mid.mean()*1e4:>7.1f} bps  (normalizer: {nmid.mean()*1e4:.1f} bps)')
print()
eff = ret_e.mean() / ret_v.mean() * 1e4
neff = norm_ret_e.mean() / norm_ret_v.mean() * 1e4
acost = -arb_e.mean() / arb_v.mean() * 1e4 if arb_v.mean() > 0 else 0
nacost = -norm_arb_e.mean() / norm_arb_v.mean() * 1e4 if norm_arb_v.mean() > 0 else 0
print(f'  Retail edge/vol: {eff:>6.2f} bps  (normalizer: {neff:.2f} bps)')
print(f'  Arb cost/vol:    {acost:>6.2f} bps  (normalizer: {nacost:.2f} bps)')
print()
pcts = [5, 25, 50, 75, 95]
vals = np.percentile(edge, pcts)
pct_str = '  '.join(f'p{p}={v:.0f}' for p, v in zip(pcts, vals))
print(f'  Edge dist:     {pct_str}')
print('=' * 65)
print()
"
rm -rf "$TMPDIR"
