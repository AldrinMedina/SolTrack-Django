from dashboard.utils.web3_balance import get_eth_balance, get_mapped_ganache_address

def wallet_balance(request):
    """Provide ETH balance globally for sidebar."""
    if not request.user.is_authenticated:
        return {}

    user = request.user

    # determine wallet address (Metamask preferred → fallback to Ganache mapping)
    wallet_addr = user.m_address or get_mapped_ganache_address(user)
    eth_balance = get_eth_balance(wallet_addr) if wallet_addr else 0

    return {
        "eth_balance": eth_balance,
        "wallet_address": wallet_addr,
    }
