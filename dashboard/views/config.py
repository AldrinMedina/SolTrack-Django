# dashboard/views/config.py

import os
from web3 import Web3

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
CHAIN_RPC =  os.getenv("GANACHE_URL")
DEPLOYER_PRIVATE_KEY =  os.getenv("DEPLOYER_PRIVATE_KEY")
DEPLOYER_ADDRESS = os.getenv("DEPLOYER_ADDRESS")
SOLC_VERSION = "0.8.19"
DEFAULT_GAS_LIMIT = int(os.getenv("DEFAULT_GAS_LIMIT", 3000000))
#CHAIN_ID = int(os.getenv("CHAIN_ID"))
CHAIN_ID = 11155111 if "sepolia" in rpc_url.lower() else 1337
MAX_FEE_GWEI = int(os.getenv("MAX_FEE_GWEI", 6))
PRIORITY_FEE_GWEI = int(os.getenv("PRIORITY_FEE_GWEI", 1))
GAS_PRICE_GWEI = 5
rpc_url = os.getenv("TESTNET_RPC_URL", "http://127.0.0.1:7545")
# ----------------------------------------------------------------------
# WEB3 INSTANCE
# ----------------------------------------------------------------------
web3 = Web3(Web3.HTTPProvider(rpc_url))
