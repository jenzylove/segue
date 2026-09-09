from __future__ import annotations

from .evm import address_word, encode_bytes_tail, selector, word

ZERO = "0x0000000000000000000000000000000000000000"


def _address(value: str) -> str:
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x") or int(value[2:], 16) == 0:
        raise ValueError("invalid transaction address")
    return value


def _market_tuple(market: dict) -> str:
    keys = ("loan_token", "collateral_token", "oracle_address", "irm_address")
    if any(not market.get(key) for key in keys) or market.get("lltv_wad") is None:
        raise ValueError("verified MarketParams are required")
    return "".join((address_word(_address(market[key])) for key in keys)) + word(int(market["lltv_wad"]))


def _call(signature: str, args: str) -> str:
    return selector(signature) + args


def plan_call(target: str, market_id: str, calldata: str, post: str, *pre: str, operation: str | None = None, amount_atomic: int | None = None, wallet: str | None = None) -> dict:
    _address(target)
    if not calldata.startswith("0x") or len(calldata) < 10:
        raise ValueError("generated calldata is malformed")
    int(calldata[2:], 16)
    out = {"chain_id": 8453, "target": target, "calldata": calldata, "value": "0", "market_id": market_id, "preconditions": list(pre), "expected_postcondition": post}
    if operation is not None: out["operation"] = operation
    if amount_atomic is not None: out["amount_atomic"] = amount_atomic
    if wallet is not None: out["wallet"] = wallet
    return out


def _approve(token: str, spender: str, amount: int, market_id: str, note: str, wallet: str | None = None) -> dict:
    if amount <= 0: raise ValueError("approval amount must be positive")
    return plan_call(token, market_id, _call("approve(address,uint256)", address_word(spender) + word(amount)), note, operation="approve", amount_atomic=amount, wallet=wallet)


def _supply(morpho: str, market_id: str, market: dict, amount: int, wallet: str) -> str:
    return _call("supply((address,address,address,address,uint256),uint256,uint256,address,bytes)", _market_tuple(market) + word(amount) + word(0) + address_word(wallet) + word(9 * 32) + encode_bytes_tail())


def _supply_collateral(morpho: str, market_id: str, market: dict, amount: int, wallet: str) -> str:
    return _call("supplyCollateral((address,address,address,address,uint256),uint256,address,bytes)", _market_tuple(market) + word(amount) + address_word(wallet) + word(8 * 32) + encode_bytes_tail())


def _borrow(market: dict, amount: int, wallet: str) -> str:
    return _call("borrow((address,address,address,address,uint256),uint256,uint256,address,address)", _market_tuple(market) + word(amount) + word(0) + address_word(wallet) + address_word(wallet))


def _repay(market: dict, assets: int, shares: int, wallet: str) -> str:
    return _call("repay((address,address,address,address,uint256),uint256,uint256,address,bytes)", _market_tuple(market) + word(assets) + word(shares) + address_word(wallet) + word(8 * 32) + encode_bytes_tail())


def _withdraw(market: dict, amount: int, wallet: str) -> str:
    return _call("withdrawCollateral((address,address,address,address,uint256),uint256,address,address)", _market_tuple(market) + word(amount) + address_word(wallet) + address_word(wallet))


def lender_supply_plan(morpho: str, usdc: str, market_id: str, amount: int, *, wallet: str, market: dict) -> dict:
    if amount <= 0: raise ValueError("supply amount must be positive")
    _address(wallet); _address(morpho); _address(usdc)
    return {"flow": "lender-supply", "actions": [_approve(usdc, morpho, amount, market_id, "lender wallet holds USDC", wallet), plan_call(morpho, market_id, _supply(morpho, market_id, market, amount, wallet), "market supplied assets increase", "USDC approval transaction confirmed", operation="supply", amount_atomic=amount, wallet=wallet)], "market": market, "signature_ready": True}


def borrower_action_plan(morpho: str, market_id: str, action: str, *, wallet: str, amount: int, market: dict) -> dict:
    if action not in {"supply", "borrow", "repay", "withdraw"}: raise ValueError("unsupported Morpho action")
    if amount <= 0: raise ValueError("action amount must be positive")
    _address(wallet); _address(morpho)
    m = _market_tuple(market)
    if action == "supply":
        return {"flow": "supply-collateral", "actions": [_approve(market["collateral_token"], morpho, amount, market_id, "borrower owns the NVDAc collateral", wallet), plan_call(morpho, market_id, _supply_collateral(morpho, market_id, market, amount, wallet), "collateral position increases", "NVDAc approval confirmed", operation="supplyCollateral", amount_atomic=amount, wallet=wallet)], "market": market, "signature_ready": True}
    if action == "borrow":
        return {"flow": "borrow", "actions": [plan_call(morpho, market_id, _borrow(market, amount, wallet), "USDC is credited to the borrower", "collateral position and safe LTV verified", operation="borrow", amount_atomic=amount, wallet=wallet)], "market": market, "signature_ready": True}
    if action == "repay":
        return {"flow": "repay", "actions": [_approve(market["loan_token"], morpho, amount, market_id, "USDC approval covers the requested repayment", wallet), plan_call(morpho, market_id, _repay(market, amount, 0, wallet), "borrow assets decrease", "fresh position has borrow shares", operation="repay", amount_atomic=amount, wallet=wallet)], "market": market, "signature_ready": True}
    return {"flow": "withdraw", "actions": [plan_call(morpho, market_id, _withdraw(market, amount, wallet), "collateral is returned to the borrower", "borrow shares are zero", operation="withdrawCollateral", amount_atomic=amount, wallet=wallet)], "market": market, "signature_ready": True}


def full_repay_plan(morpho: str, market_id: str, *, wallet: str, market: dict, borrow_shares: int, approval_amount: int) -> dict:
    if borrow_shares <= 0: raise ValueError("fresh borrow shares must be positive")
    if approval_amount <= 0: raise ValueError("USDC approval must cover accrued debt")
    _address(wallet); _address(morpho)
    return {"flow": "full-repay", "actions": [_approve(market["loan_token"], morpho, approval_amount, market_id, "USDC approval covers accrued debt", wallet), plan_call(morpho, market_id, _repay(market, 0, borrow_shares, wallet), "fresh onchain position borrow shares equal zero", "repay uses fresh borrow shares (assets=0)", operation="repayShares", amount_atomic=borrow_shares, wallet=wallet)], "market": market, "borrow_shares": borrow_shares, "approval_amount": approval_amount, "signature_ready": True}


def withdraw_plan(morpho: str, market_id: str, *, wallet: str, market: dict, collateral_amount: int) -> dict:
    if collateral_amount <= 0: raise ValueError("collateral withdrawal must be positive")
    _address(wallet); _address(morpho)
    return {"flow": "withdraw-collateral", "actions": [plan_call(morpho, market_id, _withdraw(market, collateral_amount, wallet), "collateral returns to the borrower", "fresh borrow shares are zero", operation="withdrawCollateral", amount_atomic=collateral_amount, wallet=wallet)], "market": market, "signature_ready": True}
