#!/usr/bin/env bash
set -euo pipefail

# AMM Challenge — Local Setup Script
# Run from the repo root: bash setup.sh

echo "=== 1. Installing Python package ==="
pip install -e .

echo "=== 2. Installing maturin ==="
pip install maturin

echo "=== 3. Building Rust simulation engine ==="
cd amm_sim_rs
VIRTUAL_ENV=/usr maturin develop --release
cd ..

echo "=== 4. Installing solc 0.8.24 ==="
mkdir -p ~/.solcx
if [ ! -x ~/.solcx/solc-v0.8.24 ]; then
    curl -L https://github.com/ethereum/solidity/releases/download/v0.8.24/solc-static-linux \
        -o ~/.solcx/solc-v0.8.24
    chmod +x ~/.solcx/solc-v0.8.24
    echo "solc installed."
else
    echo "solc already installed, skipping."
fi

echo "=== 5. Verifying ==="
amm-match run contracts/src/Strategy.sol --simulations 5

echo "=== Setup complete ==="
