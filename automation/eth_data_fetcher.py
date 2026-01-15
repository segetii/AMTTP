"""
AMTTP - Ethereum Data Fetcher

Downloads historical Ethereum transactions for fraud scoring.

Data Sources:
1. Etherscan API (free tier) - for targeted address lookups
2. Google BigQuery public dataset - for bulk historical data
3. Sample/synthetic data - for testing

Note: For production, consider Alchemy/Infura for higher rate limits.
"""
import os
import json
import time
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")  # Get free key from etherscan.io
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


@dataclass
class EthTransaction:
    """Ethereum transaction data."""
    tx_hash: str
    block_number: int
    timestamp: int
    from_address: str
    to_address: str
    value_eth: float
    gas_price_gwei: float
    gas_used: int
    is_error: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EtherscanFetcher:
    """Fetch transactions from Etherscan API."""
    
    BASE_URL = "https://api.etherscan.io/api"
    RATE_LIMIT = 5  # calls per second (free tier)
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or ETHERSCAN_API_KEY
        self._last_call = 0
    
    async def _rate_limit(self):
        """Respect rate limits."""
        elapsed = time.time() - self._last_call
        if elapsed < 1.0 / self.RATE_LIMIT:
            await asyncio.sleep(1.0 / self.RATE_LIMIT - elapsed)
        self._last_call = time.time()
    
    async def get_transactions(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99999999,
        page: int = 1,
        offset: int = 100,
    ) -> List[EthTransaction]:
        """Get transactions for an address."""
        await self._rate_limit()
        
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": "desc",
            "apikey": self.api_key,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(self.BASE_URL, params=params) as resp:
                data = await resp.json()
        
        if data["status"] != "1":
            logger.warning(f"Etherscan API error: {data.get('message', 'Unknown')}")
            return []
        
        transactions = []
        for tx in data.get("result", []):
            try:
                transactions.append(EthTransaction(
                    tx_hash=tx["hash"],
                    block_number=int(tx["blockNumber"]),
                    timestamp=int(tx["timeStamp"]),
                    from_address=tx["from"].lower(),
                    to_address=tx["to"].lower() if tx["to"] else "",
                    value_eth=int(tx["value"]) / 1e18,
                    gas_price_gwei=int(tx["gasPrice"]) / 1e9,
                    gas_used=int(tx["gasUsed"]),
                    is_error=tx.get("isError", "0") == "1",
                ))
            except Exception as e:
                logger.debug(f"Failed to parse tx: {e}")
        
        return transactions
    
    async def get_internal_transactions(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99999999,
    ) -> List[EthTransaction]:
        """Get internal transactions (contract calls)."""
        await self._rate_limit()
        
        params = {
            "module": "account",
            "action": "txlistinternal",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "sort": "desc",
            "apikey": self.api_key,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(self.BASE_URL, params=params) as resp:
                data = await resp.json()
        
        if data["status"] != "1":
            return []
        
        transactions = []
        for tx in data.get("result", []):
            try:
                transactions.append(EthTransaction(
                    tx_hash=tx.get("hash", tx.get("traceId", "")),
                    block_number=int(tx["blockNumber"]),
                    timestamp=int(tx["timeStamp"]),
                    from_address=tx["from"].lower(),
                    to_address=tx["to"].lower() if tx["to"] else "",
                    value_eth=int(tx["value"]) / 1e18,
                    gas_price_gwei=0,
                    gas_used=int(tx.get("gasUsed", 0)),
                    is_error=tx.get("isError", "0") == "1",
                ))
            except Exception as e:
                logger.debug(f"Failed to parse internal tx: {e}")
        
        return transactions


class SyntheticDataGenerator:
    """
    Generate synthetic Ethereum-like transactions for testing.
    
    Creates realistic patterns including:
    - Normal user activity
    - Exchange deposits/withdrawals
    - DeFi interactions
    - Suspicious patterns (mixer-like, wash trading)
    """
    
    # Known address patterns (for demo)
    EXCHANGES = [
        "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549",  # Binance
        "0xdfd5293d8e347dfe59e90efd55b2956a1343963d",  # Binance
        "0x56eddb7aa87536c09ccc2793473599fd21a8b17f",  # Coinbase
        "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43",  # Coinbase
    ]
    
    MIXERS = [
        "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",  # Tornado Cash
        "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",  # Tornado Cash
        "0x4736dcf1b7a3d580672cce6e7c65cd5cc9cfba9d",  # Mixer
    ]
    
    SANCTIONED = [
        "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c",
        "0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b",
        "0x7f367cc41522ce07553e823bf3be79a889debe1b",
    ]
    
    DEFI_CONTRACTS = [
        "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # Uniswap Router
        "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",  # Uniswap V3
        "0xdef1c0ded9bec7f1a1670819833240f027b25eff",  # 0x Exchange
    ]
    
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.addresses: List[str] = []
        self._generate_addresses(500)  # Generate pool of addresses
    
    def _generate_addresses(self, count: int):
        """Generate random Ethereum addresses."""
        for _ in range(count):
            addr = "0x" + "".join(random.choices("0123456789abcdef", k=40))
            self.addresses.append(addr)
    
    def _random_address(self, include_special: bool = True) -> str:
        """Get a random address with occasional special addresses."""
        if include_special and random.random() < 0.1:
            special_type = random.random()
            if special_type < 0.4:
                return random.choice(self.EXCHANGES)
            elif special_type < 0.6:
                return random.choice(self.DEFI_CONTRACTS)
            elif special_type < 0.8:
                return random.choice(self.MIXERS)
            else:
                return random.choice(self.SANCTIONED)
        return random.choice(self.addresses)
    
    def generate_transactions(
        self,
        count: int = 10000,
        days: int = 7,
    ) -> List[EthTransaction]:
        """Generate synthetic transactions."""
        now = int(time.time())
        start_ts = now - (days * 24 * 3600)
        
        transactions = []
        block_number = 19000000  # Approximate recent block
        
        for i in range(count):
            # Random timestamp within the period
            ts = random.randint(start_ts, now)
            
            # Determine transaction type
            tx_type = random.random()
            
            if tx_type < 0.6:
                # Normal P2P transfer
                from_addr = self._random_address(include_special=False)
                to_addr = self._random_address(include_special=True)
                value = random.expovariate(1/0.5)  # Avg 0.5 ETH
            elif tx_type < 0.8:
                # Exchange interaction
                if random.random() < 0.5:
                    # Deposit to exchange
                    from_addr = self._random_address(include_special=False)
                    to_addr = random.choice(self.EXCHANGES)
                else:
                    # Withdrawal from exchange
                    from_addr = random.choice(self.EXCHANGES)
                    to_addr = self._random_address(include_special=False)
                value = random.expovariate(1/2.0)  # Larger amounts
            elif tx_type < 0.9:
                # DeFi interaction
                from_addr = self._random_address(include_special=False)
                to_addr = random.choice(self.DEFI_CONTRACTS)
                value = random.expovariate(1/1.0)
            elif tx_type < 0.95:
                # Suspicious: Mixer interaction
                if random.random() < 0.5:
                    from_addr = self._random_address(include_special=False)
                    to_addr = random.choice(self.MIXERS)
                else:
                    from_addr = random.choice(self.MIXERS)
                    to_addr = self._random_address(include_special=False)
                # Mixers often use round numbers
                value = random.choice([0.1, 1.0, 10.0, 100.0])
            else:
                # Suspicious: Sanctioned address interaction
                if random.random() < 0.5:
                    from_addr = random.choice(self.SANCTIONED)
                    to_addr = self._random_address(include_special=False)
                else:
                    from_addr = self._random_address(include_special=False)
                    to_addr = random.choice(self.SANCTIONED)
                value = random.expovariate(1/5.0)
            
            tx = EthTransaction(
                tx_hash=f"0x{''.join(random.choices('0123456789abcdef', k=64))}",
                block_number=block_number + (i // 10),
                timestamp=ts,
                from_address=from_addr,
                to_address=to_addr,
                value_eth=round(value, 6),
                gas_price_gwei=round(random.uniform(10, 100), 2),
                gas_used=random.randint(21000, 200000),
                is_error=random.random() < 0.01,
            )
            transactions.append(tx)
        
        # Sort by timestamp
        transactions.sort(key=lambda x: x.timestamp)
        
        return transactions
    
    def generate_wash_trading_pattern(
        self,
        num_addresses: int = 5,
        num_rounds: int = 10,
    ) -> List[EthTransaction]:
        """Generate wash trading pattern (circular transfers)."""
        addresses = [self._random_address(include_special=False) for _ in range(num_addresses)]
        now = int(time.time())
        
        transactions = []
        block = 19000000
        
        for round_num in range(num_rounds):
            # Circular: A->B->C->D->E->A
            for i in range(num_addresses):
                from_idx = i
                to_idx = (i + 1) % num_addresses
                
                tx = EthTransaction(
                    tx_hash=f"0x{''.join(random.choices('0123456789abcdef', k=64))}",
                    block_number=block + round_num * num_addresses + i,
                    timestamp=now - (num_rounds - round_num) * 3600,
                    from_address=addresses[from_idx],
                    to_address=addresses[to_idx],
                    value_eth=10.0,  # Same amount each time
                    gas_price_gwei=25.0,
                    gas_used=21000,
                )
                transactions.append(tx)
        
        return transactions


def save_transactions(transactions: List[EthTransaction], filename: str):
    """Save transactions to JSON file."""
    filepath = DATA_DIR / filename
    with open(filepath, 'w') as f:
        json.dump([tx.to_dict() for tx in transactions], f, indent=2)
    logger.info(f"Saved {len(transactions)} transactions to {filepath}")
    return filepath


def load_transactions(filename: str) -> List[EthTransaction]:
    """Load transactions from JSON file."""
    filepath = DATA_DIR / filename
    with open(filepath, 'r') as f:
        data = json.load(f)
    return [EthTransaction(**tx) for tx in data]


async def fetch_real_data(addresses: List[str], days: int = 7) -> List[EthTransaction]:
    """
    Fetch real transaction data from Etherscan.
    
    Note: Requires ETHERSCAN_API_KEY environment variable.
    """
    if not ETHERSCAN_API_KEY:
        logger.warning("No ETHERSCAN_API_KEY set. Using synthetic data instead.")
        return []
    
    fetcher = EtherscanFetcher()
    all_transactions = []
    
    for address in addresses:
        logger.info(f"Fetching transactions for {address}")
        txs = await fetcher.get_transactions(address, offset=1000)
        all_transactions.extend(txs)
        
        # Also get internal transactions
        internal_txs = await fetcher.get_internal_transactions(address)
        all_transactions.extend(internal_txs)
    
    # Filter to last N days
    cutoff = int(time.time()) - (days * 24 * 3600)
    all_transactions = [tx for tx in all_transactions if tx.timestamp >= cutoff]
    
    # Deduplicate by tx_hash
    seen = set()
    unique_txs = []
    for tx in all_transactions:
        if tx.tx_hash not in seen:
            seen.add(tx.tx_hash)
            unique_txs.append(tx)
    
    return unique_txs


def generate_demo_dataset(
    num_transactions: int = 10000,
    days: int = 7,
    include_wash_trading: bool = True,
) -> List[EthTransaction]:
    """Generate a demo dataset for testing."""
    generator = SyntheticDataGenerator()
    
    # Generate main transactions
    transactions = generator.generate_transactions(num_transactions, days)
    
    # Add wash trading patterns
    if include_wash_trading:
        wash_trades = generator.generate_wash_trading_pattern(num_addresses=5, num_rounds=20)
        transactions.extend(wash_trades)
        transactions.sort(key=lambda x: x.timestamp)
    
    return transactions


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch/generate Ethereum transaction data")
    parser.add_argument("--mode", choices=["synthetic", "real"], default="synthetic")
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output", type=str, default="eth_transactions.json")
    
    args = parser.parse_args()
    
    if args.mode == "synthetic":
        print(f"Generating {args.count} synthetic transactions for {args.days} days...")
        transactions = generate_demo_dataset(args.count, args.days)
    else:
        # Real data requires addresses to track
        # These are some high-activity addresses
        addresses = [
            "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance Hot Wallet
            "0xdfd5293d8e347dfe59e90efd55b2956a1343963d",  # Binance
        ]
        transactions = asyncio.run(fetch_real_data(addresses, args.days))
    
    filepath = save_transactions(transactions, args.output)
    print(f"\nSaved {len(transactions)} transactions to {filepath}")
    
    # Print sample
    print("\nSample transactions:")
    for tx in transactions[:5]:
        print(f"  {tx.tx_hash[:16]}... | {tx.from_address[:10]}... -> {tx.to_address[:10]}... | {tx.value_eth:.4f} ETH")
