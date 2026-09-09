"""Generate real Morpho Blue ABI calldata with Foundry's official ABI encoder.
No transaction is signed or broadcast; MORPHO_BLUE_ADDRESS is required."""
from __future__ import annotations
import argparse, os, subprocess

def encode(signature: str, args: list[str]) -> str:
    result = subprocess.run(["cast", "calldata", signature, *args], text=True, capture_output=True)
    if result.returncode: raise RuntimeError(result.stderr.strip() or "cast calldata failed")
    return result.stdout.strip()

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("action", choices=["supply","borrow","repay","withdraw","lender-supply"]); p.add_argument("market_id"); p.add_argument("loan_token"); p.add_argument("collateral_token"); p.add_argument("oracle"); p.add_argument("irm"); p.add_argument("lltv"); p.add_argument("amount", type=int); p.add_argument("on_behalf"); p.add_argument("receiver"); a=p.parse_args()
    target=os.environ.get("MORPHO_BLUE_ADDRESS", "")
    if not target: raise SystemExit("BLOCKED: MORPHO_BLUE_ADDRESS must be supplied from the verified Morpho deployment")
    m=f"({a.loan_token},{a.collateral_token},{a.oracle},{a.irm},{a.lltv})"
    if a.action == "lender-supply": sig="supply((address,address,address,address,uint256),uint256,uint256,address,bytes)"; args=[m,str(a.amount),"0",a.on_behalf,"0x"]
    elif a.action == "supply": sig="supplyCollateral((address,address,address,address,uint256),uint256,address,bytes)"; args=[m,str(a.amount),a.on_behalf,"0x"]
    elif a.action == "borrow": sig="borrow((address,address,address,address,uint256),uint256,uint256,address,address)"; args=[m,str(a.amount),"0",a.on_behalf,a.receiver]
    elif a.action == "repay": sig="repay((address,address,address,address,uint256),uint256,uint256,address,bytes)"; args=[m,str(a.amount),"0",a.on_behalf,"0x"]
    else: sig="withdrawCollateral((address,address,address,address,uint256),uint256,address,address)"; args=[m,str(a.amount),a.on_behalf,a.receiver]
    calldata=encode(sig,args)
    print({"chain_id":8453,"target":target,"calldata":calldata,"value":"0","market_id":a.market_id,"preconditions":["MarketParams match verified onchain market","wallet signature required"],"expected_postcondition":a.action})
    return 0
if __name__ == "__main__": raise SystemExit(main())
