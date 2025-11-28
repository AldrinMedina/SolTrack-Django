from web3 import Web3
import os

# ⚠ Ganache RPC (current environment)
GANACHE_RPC = "http://127.0.0.1:7545"

# ⚠ Sepolia (future)
# SEPOLIA_RPC = "https://sepolia.infura.io/v3/YOUR_INFURA_KEY"

#w3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC ))
SEPOLIA_URL = os.getenv("TESTNET_RPC_URL")

web3 = Web3(Web3.HTTPProvider(SEPOLIA_URL))

def get_eth_balance(address):
    try:
        wei_balance = web3.eth.get_balance(address)
        return web3.from_wei(wei_balance, "ether")
    except Exception as e:
        print(f"[ERR] balance fetch failed: {e}")
        return 0

