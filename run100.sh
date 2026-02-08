#!/bin/bash
# Run 100 sims in 4 sequential batches of 25, each in a fresh process
SOL=${1:-contracts/src/Strategy.sol}
TOTAL=0
for start in 0 25 50 75; do
    EDGE=$(python run_batch.py "$SOL" $start 25 2>/dev/null)
    if [ $? -ne 0 ]; then
        echo "FAILED at batch starting seed $start"
        exit 1
    fi
    TOTAL=$(python -c "print(${TOTAL} + ${EDGE})")
    echo "  batch $start-$((start+24)): edge_sum=$EDGE  running_total=$TOTAL"
done
AVG=$(python -c "print(f'{${TOTAL}/100:.2f}')")
echo "Edge (100 sims): $AVG"
