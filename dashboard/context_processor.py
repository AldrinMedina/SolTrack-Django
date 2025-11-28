from dashboard.utils.web3_balance import get_eth_balance

def wallet_balance(request):
    """Provide ETH balance globally for sidebar."""
    if not request.user.is_authenticated:
        return {}

    wallet_addr = request.user.m_address   # always use Sepolia wallet
    eth_balance = get_eth_balance(wallet_addr) if wallet_addr else 0

    return {
        "eth_balance": eth_balance,
        "wallet_address": wallet_addr,
    }
