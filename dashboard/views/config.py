# dashboard/views/config.py

import os
from web3 import Web3

# ----------------------------------------------------------------------
# RPC / NETWORK
# ----------------------------------------------------------------------
rpc_url = os.getenv("TESTNET_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")

if not rpc_url:
    raise RuntimeError("TESTNET_RPC_URL is not set")


# Detect chain
CHAIN_ID = 11155111 if "sepolia" in rpc_url.lower() else 1337

# ----------------------------------------------------------------------
# DEPLOYER
# ----------------------------------------------------------------------
DEPLOYER_PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")
DEPLOYER_ADDRESS = os.getenv("DEPLOYER_ADDRESS")

# ----------------------------------------------------------------------
# GAS / FEES
# ----------------------------------------------------------------------
SOLC_VERSION = "0.8.19"
DEFAULT_GAS_LIMIT = int(os.getenv("DEFAULT_GAS_LIMIT", 3_000_000))
MAX_FEE_GWEI = int(os.getenv("MAX_FEE_GWEI", 6))
PRIORITY_FEE_GWEI = int(os.getenv("PRIORITY_FEE_GWEI", 1))
GAS_PRICE_GWEI = int(os.getenv("GAS_PRICE_GWEI", 5))

# ----------------------------------------------------------------------
# WEB3 INSTANCE
# ----------------------------------------------------------------------
web3 = Web3(Web3.HTTPProvider(rpc_url))
print("RPC URL:", rpc_url)
print("Chain ID from node:", web3.eth.chain_id)
