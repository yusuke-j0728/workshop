from web3 import Web3
import datetime
import io
import sys
from decimal import Decimal

# ──────────────────────────────────────────────
#  Minimal ABIs
# ──────────────────────────────────────────────
uniswap_v2_factory_abi = [
    {
        "constant": True,
        "inputs": [{"name": "tokenA", "type": "address"},
                   {"name": "tokenB", "type": "address"}],
        "name": "getPair",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

pair_abi = [
    {"constant": True, "inputs": [], "name": "token0",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "token1",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply",
     "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "getReserves",
     "outputs": [{"name": "reserve0", "type": "uint112"},
                 {"name": "reserve1", "type": "uint112"},
                 {"name": "blockTimestampLast", "type": "uint32"}],
     "stateMutability": "view", "type": "function"}
]

token_abi = [
    {"constant": True, "inputs": [], "name": "name",
     "outputs": [{"name": "", "type": "string"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol",
     "outputs": [{"name": "", "type": "string"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply",
     "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}],
     "stateMutability": "view", "type": "function"},
    # ↓　Ownership 解析用（存在しない場合は try/except）
    {"constant": True, "inputs": [], "name": "owner",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"}
]

# ──────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────
BASE_RPC_URL = "https://base.drpc.org"
input_token_address = "0x768BE13e1680b5ebE0024C42c896E3dB59ec0149"
uniswap_v2_factory_address = "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6"
USDC_contract = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
WETH_contract = "0x4200000000000000000000000000000000000006"
ZERO_address = "0x0000000000000000000000000000000000000000"

web3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
if web3.is_connected():
    print("Connected to Base Chain")

factory_contract = web3.eth.contract(
    address=web3.to_checksum_address(uniswap_v2_factory_address),
    abi=uniswap_v2_factory_abi
)

# ──────────────────────────────────────────────
#  Existing
# ──────────────────────────────────────────────
def get_token_decimals(token_address):
    if token_address.lower() == USDC_contract.lower():
        return 6
    if token_address.lower() == WETH_contract.lower():
        return 18
    token_contract = web3.eth.contract(address=web3.to_checksum_address(token_address),
                                       abi=token_abi)
    return token_contract.functions.decimals().call()

def get_token_total_supply(token_address):
    token_contract = web3.eth.contract(address=web3.to_checksum_address(token_address),
                                       abi=token_abi)
    return token_contract.functions.totalSupply().call()

def check_minting_ability(token_contract):
    try:
        token_contract.functions.mint().call()
        return {"mintable": True, "supplyStatus": "NOT FIXED"}
    except Exception:
        return {"mintable": False, "supplyStatus": "FIXED"}

def find_pair_by_token(token_address):
    pair_address_usdc = factory_contract.functions.getPair(
        web3.to_checksum_address(token_address),
        web3.to_checksum_address(USDC_contract)
    ).call()
    if pair_address_usdc != ZERO_address:
        return {"pairAddress": pair_address_usdc, "quoteToken": "USDC"}

    pair_address_weth = factory_contract.functions.getPair(
        web3.to_checksum_address(token_address),
        web3.to_checksum_address(WETH_contract)
    ).call()
    if pair_address_weth != ZERO_address:
        return {"pairAddress": pair_address_weth, "quoteToken": "WETH"}
    return None

def calculate_market_cap(pair_contract):
    try:
        reserves = pair_contract.functions.getReserves().call()
        token0 = pair_contract.functions.token0().call()
        token1 = pair_contract.functions.token1().call()
        total_supply = get_token_total_supply(token0)

        res0_norm = Decimal(reserves[0]) / Decimal(10 ** get_token_decimals(token0))
        res1_norm = Decimal(reserves[1]) / Decimal(10 ** get_token_decimals(token1))
        price = res1_norm / res0_norm
        supply_norm = Decimal(total_supply) / Decimal(10 ** get_token_decimals(token0))
        market_cap = supply_norm * price
        return {
            "reserves": reserves,
            "pricePerToken": str(price),
            "totalSupplyNormalized": str(supply_norm),
            "marketCap": str(market_cap)
        }
    except Exception as e:
        print("Error calculating market cap:", e)
        return None

# ──────────────────────────────────────────────
#  New
# ──────────────────────────────────────────────
def get_owner_address(token_contract):
    try:
        return token_contract.functions.owner().call()
    except Exception:
        return None

def calculate_liquidity_share(input_token_addr, pair_contract):
    try:
        reserves = pair_contract.functions.getReserves().call()
        token0 = pair_contract.functions.token0().call()
        reserve_input = reserves[0] if input_token_addr.lower() == token0.lower() else reserves[1]
        total_supply = get_token_total_supply(input_token_addr)
        return (Decimal(reserve_input) / Decimal(total_supply)) if total_supply else Decimal("0")
    except Exception:
        return Decimal("0")

def assess_risk(owner_addr, mintable, liquidity_share, quote_token_symbol,
                quote_reserve_raw):
    score = 0
    flags = []

    if owner_addr and owner_addr.lower() != ZERO_address.lower():
        score += 2
        flags.append("Ownership not renounced")

    if mintable:
        score += 3
        flags.append("Token is mintable")

    if liquidity_share < Decimal("0.05"):
        score += 2
        flags.append("Low liquidity share (<5%)")

    # Micro-liquidity
    quote_decimals = 6 if quote_token_symbol == "USDC" else 18
    quote_reserve_norm = Decimal(quote_reserve_raw) / Decimal(10 ** quote_decimals)
    if quote_token_symbol == "USDC" and quote_reserve_norm < Decimal("5000"):
        score += 3
        flags.append("<5 000 USDC liquidity")
    if quote_token_symbol == "WETH" and quote_reserve_norm < Decimal("5"):
        score += 3
        flags.append("<5 WETH liquidity")

    level = ("LOW" if score <= 3 else
             "MEDIUM" if score <= 5 else
             "HIGH" if score <= 7 else
             "CRITICAL")
    return score, level, flags, quote_reserve_norm

# ──────────────────────────────────────────────
#  Main execution
# ──────────────────────────────────────────────
pair_info = find_pair_by_token(input_token_address)
if pair_info is None:
    raise SystemExit("Pair could not be found! Abort.")

pair_address = pair_info["pairAddress"]
pair_contract = web3.eth.contract(
    address=web3.to_checksum_address(pair_address),
    abi=pair_abi
)

# Token roles
token0 = pair_contract.functions.token0().call()
token1 = pair_contract.functions.token1().call()
input_token = token0 if token0.lower() not in (USDC_contract.lower(), WETH_contract.lower()) else token1
pair_token = token1 if input_token.lower() == token0.lower() else token0
quote_token_symbol = pair_info["quoteToken"]

# Contract handles
token_contract = web3.eth.contract(address=input_token, abi=token_abi)
pair_token_contract = web3.eth.contract(address=pair_token, abi=token_abi)

# ─── Capture stdout to buffer ───
buffer = io.StringIO()
sys.stdout = buffer

# ======= 既存レポート =======
print("=" * 80)
print("🔍 TOKEN ANALYSIS REPORT")
print("=" * 80)
print("Generated on:", datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
print("-" * 80)

print("\n📊 TOKEN INFORMATION")
print("-" * 40)
token_name = token_contract.functions.name().call()
token_symbol = token_contract.functions.symbol().call()
print("Token Address:", input_token)
print("Token Name:", token_name)
print("Token Symbol:", token_symbol)

print("\n🔄 PAIR TOKEN INFORMATION")
print("-" * 40)
pair_token_name = pair_token_contract.functions.name().call()
pair_token_symbol = pair_token_contract.functions.symbol().call()
print("Pair Token Address:", pair_token)
print("Pair Token Name:", pair_token_name)
print("Pair Token Symbol:", pair_token_symbol)

print("\n💧 LIQUIDITY INFORMATION")
print("-" * 40)
total_lp_tokens = pair_contract.functions.totalSupply().call()
print("Liquidity Pair Address:", pair_address)
print("Total Supply of LP Tokens:", total_lp_tokens)

print("\n💰 MARKET ANALYSIS")
print("-" * 40)
market_cap_data = calculate_market_cap(pair_contract)
if market_cap_data:
    print(f"Reserve {token_symbol}:", market_cap_data["reserves"][0])
    print(f"Reserve {pair_token_symbol}:", market_cap_data["reserves"][1])
    print(f"Price per {token_symbol}:", market_cap_data["pricePerToken"], pair_token_symbol)
    print("Total Supply:", market_cap_data["totalSupplyNormalized"])
    print("Market Cap:", market_cap_data["marketCap"], pair_token_symbol)

print("\n🪄 SUPPLY ANALYSIS")
print("-" * 40)
minting_info = check_minting_ability(token_contract)
print("Mint Status:", "MINTABLE" if minting_info["mintable"] else "NOT MINTABLE")
print("Total Supply Status:", minting_info["supplyStatus"])

# ======= 追加：🛡️ RUG-PULL RISK ANALYSIS =======
print("\n🛡️ RUG-PULL RISK ANALYSIS")
print("-" * 40)
owner_addr = get_owner_address(token_contract)
liquidity_share = calculate_liquidity_share(input_token, pair_contract)
risk_score, risk_level, risk_flags, quote_reserve_norm = assess_risk(
    owner_addr,
    minting_info["mintable"],
    liquidity_share,
    quote_token_symbol,
    market_cap_data["reserves"][1]  # quote side reserve raw
)

print("Owner Address:", owner_addr if owner_addr else "N/A (renounced or not Ownable)")
print(f"Liquidity Share (LP / Total): {liquidity_share * 100:.4f}%")
if quote_token_symbol == "USDC":
    print("USDC Reserve in LP:", f"{quote_reserve_norm:,.0f} USDC")
else:
    print("WETH Reserve in LP:", f"{quote_reserve_norm:.4f} WETH")

print(f"Risk Score (0–10): {risk_score}")
print("Risk Level:", risk_level)
if risk_flags:
    print("Risk Flags:")
    for f in risk_flags:
        print(" •", f)

print("\n" + "=" * 80)
print("End of Report")
print("=" * 80)

sys.stdout = sys.__stdout__

output_text = buffer.getvalue()

# Save to text file
txt_filename = '/data/outputs/report.txt'
with open(txt_filename, 'w') as f:
    f.write(output_text)

print(f"✅ Output saved to {txt_filename} \n")
print(output_text)

# ───
