from web3 import Web3

# ⚠ Ganache RPC (current environment)
GANACHE_RPC = "http://127.0.0.1:7545"

# ⚠ Sepolia (future)
# SEPOLIA_RPC = "https://sepolia.infura.io/v3/YOUR_INFURA_KEY"

#w3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC ))

w3 = Web3(Web3.HTTPProvider(GANACHE_RPC))

def get_eth_balance(address: str) -> float:
    """Returns ETH balance for a wallet address in float ETH."""
    try:
        balance_wei = w3.eth.get_balance(address)
        balance_eth = w3.from_wei(balance_wei, "ether")
        return float(balance_eth)
    except Exception:
        return 0.0
GANACHE_ACCOUNTS = [
    # Index 0 = Admin-Alpha
    # Index 1 = Seller-Alpha
    # Index 2 = Buyer-Alpha
    # ... add more if needed
]

def get_mapped_ganache_address(user):
    """Temporary Ganache identity → address mapping based on full_name."""
    try:
        accounts = w3.eth.accounts
    except Exception:
        return None

    if user.full_name == "Admin-Alpha" and len(accounts) > 0:
        return accounts[0]
    if user.full_name == "Seller-Alpha" and len(accounts) > 1:
        return accounts[1]
    if user.full_name == "Buyer-Alpha" and len(accounts) > 2:
        return accounts[2]
    return None
