from dashboard.utils.web3_balance import get_eth_balance
def wallet_balance(request):
    if not request.user.is_authenticated:
        return {}
    wallet_addr = getattr(request.user, "m_address", None)
    eth_balance = get_eth_balance(wallet_addr) if wallet_addr else 0
    return {
        "eth_balance": eth_balance,
        "wallet_address": wallet_addr,
    }
