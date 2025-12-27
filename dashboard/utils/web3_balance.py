from web3 import Web3
import os

GANACHE_RPC = "HTTP://127.0.0.1:7545"
os.getenv("TESTNET_RPC_URL", "http://127.0.0.1:7545")

def get_eth_balance(address):
    try:
        wei_balance = web3.eth.get_balance(address)
        return web3.from_wei(wei_balance, "ether")
    except Exception as e:
        print(f"[ERR] balance fetch failed: {e}")
        return 0

