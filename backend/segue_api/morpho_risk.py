from __future__ import annotations
from decimal import Decimal

def proposal(market: dict, collateral_atomic: int, collateral_decimals: int, collateral_price: Decimal, debt_decimals: int, requested_debt_atomic: int, reserve_bps: int = 2000) -> dict:
    if collateral_atomic <= 0 or collateral_price <= 0 or requested_debt_atomic <= 0: raise ValueError("amounts and price must be positive")
    value = Decimal(collateral_atomic) / (Decimal(10) ** collateral_decimals) * collateral_price
    lltv = Decimal(market["lltv_wad"]) / Decimal(10**18)
    protocol_max = value * lltv * (Decimal(10) ** debt_decimals)
    safe_max = protocol_max * Decimal(10000-reserve_bps) / Decimal(10000)
    requested_ltv = Decimal(requested_debt_atomic) / (Decimal(10) ** debt_decimals) / value
    available = int(market.get("_available", 0))
    executable = min(int(safe_max), available)
    return {"collateral_value_usd": str(value), "protocol_max_debt_atomic": int(protocol_max), "safe_max_debt_atomic": int(safe_max), "requested_ltv": str(requested_ltv), "lltv": str(lltv), "safety_buffer_bps": reserve_bps, "available_executable_borrow_atomic": executable, "requested_debt_atomic": requested_debt_atomic, "state": "WAITING_FOR_LIQUIDITY" if available == 0 else ("PROPOSED" if requested_debt_atomic <= executable else "NEEDS_APPROVAL")}
