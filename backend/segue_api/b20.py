from __future__ import annotations

"""Verified Coinbase Tokenized Stock catalogue for Base.

The registry is deliberately small and provenance-first.  Addresses are copied
from Base's official stocks listing and are still checked for bytecode/metadata
at read time.  Capability flags describe what Segue has actually verified:
portfolio discovery is broader than the currently proven Morpho credit rail.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from .morpho import CANONICAL_COLLATERAL, USDC_BASE, discover_qualified_market, erc20_balance, rpc_call
from .evm import address_word, selector

BASE_CHAIN_ID = 8453
BASE_STOCKS_SOURCE = "https://brand.base.org/stocks"


@dataclass(frozen=True)
class B20Asset:
    ticker: str
    company: str
    address: str
    decimals: int
    sequence_supported: bool
    credit_supported: bool
    feed_status: str
    provenance: str = BASE_STOCKS_SOURCE
    acquisition_url: str = BASE_STOCKS_SOURCE


# These five assets are listed by Base's official Coinbase Tokenized Stocks
# catalogue.  Only NVDAc has a verified Segue Chainlink/Morpho credit rail;
# other assets remain portfolio-only until their feed/route is independently
# verified.  Keep this list intentionally conservative.
B20_REGISTRY: tuple[B20Asset, ...] = (
    B20Asset("NVDAc", "NVIDIA", CANONICAL_COLLATERAL, 8, True, True, "verified Chainlink total-return feed"),
    B20Asset("METAc", "Meta", "0xb2000000000000000000008bC8786B856E61707C", 8, False, False, "catalogue verified; Segue feed pending"),
    B20Asset("AAPLc", "Apple", "0xb200000000000000000000C2e324d24d7eEcd1fb", 8, False, False, "catalogue verified; Segue feed pending"),
    B20Asset("GOOGLc", "Alphabet", "0xb2000000000000000000002D0BA3164cc74f58B7", 8, False, False, "catalogue verified; Segue feed pending"),
    B20Asset("AMZNc", "Amazon", "0xb200000000000000000000d9192b6B456483C2E8", 8, False, False, "catalogue verified; Segue feed pending"),
)


def _metadata(rpc: str, asset: B20Asset) -> dict[str, Any]:
    code = rpc_call(rpc, "eth_getCode", [asset.address, "latest"])
    if not isinstance(code, str) or code in ("0x", "0x0"):
        raise ValueError("token has no Base bytecode")
    raw_decimals = rpc_call(rpc, "eth_call", [{"to": asset.address, "data": selector("decimals()")}, "latest"])
    decimals = int(str(raw_decimals), 16)
    if decimals > 18:
        raise ValueError(f"token reports unsupported decimals={decimals}")
    # symbol() is optional metadata; a non-standard token must not make the
    # wallet portfolio unavailable, so retain the verified registry ticker.
    symbol = asset.ticker
    try:
        raw_symbol = rpc_call(rpc, "eth_call", [{"to": asset.address, "data": selector("symbol()")}, "latest"])
        if isinstance(raw_symbol, str) and len(raw_symbol) >= 130:
            body = bytes.fromhex(raw_symbol[2:])
            offset = int.from_bytes(body[:32], "big")
            length = int.from_bytes(body[offset:offset + 32], "big")
            decoded = body[offset + 32:offset + 32 + length].decode("utf-8", "ignore").strip()
            if decoded:
                symbol = decoded
    except Exception:
        pass
    return {"bytecode_present": True, "decimals": decimals, "symbol": symbol}


def portfolio_for_wallet(rpc: str, wallet: str) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    for asset in B20_REGISTRY:
        item = asdict(asset)
        item["chain_id"] = BASE_CHAIN_ID
        item["balance_atomic"] = None
        item["balance"] = None
        item["market_context"] = None
        item["status"] = "UNAVAILABLE"
        try:
            metadata = _metadata(rpc, asset)
            balance = erc20_balance(rpc, asset.address, wallet)
            decimals = int(metadata["decimals"])
            item.update(metadata, balance_atomic=balance, balance=str(Decimal(balance) / (Decimal(10) ** decimals)), status="LIVE")
            if asset.credit_supported:
                item["credit_label"] = "Verified Morpho credit rail"
                try:
                    live_market = discover_qualified_market(rpc)
                    item["market_context"] = {"rail": "Morpho", "market_id": live_market["market_id"], "loan_token": live_market["loan_token"], "available_liquidity": live_market.get("available_liquidity"), "oracle_price_1e36": live_market.get("direct_oracle_price")}
                except Exception as exc:
                    item["market_context_error"] = str(exc)
            else:
                item["credit_label"] = "Credit rail not verified"
        except Exception as exc:
            item["error"] = str(exc)
            item["credit_label"] = "Credit rail not verified"
        assets.append(item)
    return {
        "wallet": wallet,
        "chain_id": BASE_CHAIN_ID,
        "assets": assets,
        "registry_source": BASE_STOCKS_SOURCE,
        "catalogue_policy": "Official Base-listed Coinbase Tokenized Stocks; capabilities are verified per asset.",
    }


def registry_public() -> list[dict[str, Any]]:
    return [asdict(asset) | {"chain_id": BASE_CHAIN_ID} for asset in B20_REGISTRY]
