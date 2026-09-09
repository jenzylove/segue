from __future__ import annotations
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.segue_api.mission import Mission, MissionState, MissionStore
from backend.segue_api.morpho import borrower_position, market_state, LOCKED_MARKET_ID, rpc_call

WALLET="0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA"
APPROVAL="0x54851555018424d3d9474fefcfc977fa12950450a0a92762b803a8df1bcfe24d"
SUPPLY="0x934f5a9241ccc429acdc5672427dc46e2d30b940d030b6801336efce357df953"
BORROW="0x341e9afc0ea0a09c81e0e64332f0283257cc5b3727db222d9f0a50b5d50963f5"
def main():
 store=MissionStore(); position=borrower_position("https://api.morpho.org",LOCKED_MARKET_ID,WALLET); state=market_state("https://api.morpho.org",LOCKED_MARKET_ID)
 rpc=os.environ.get("BASE_RPC_URL", "")
 if not rpc: raise RuntimeError("BASE_RPC_URL is required for receipt evidence")
 receipt=rpc_call(rpc,"eth_getTransactionReceipt",[BORROW])
 receipt_evidence={"status": receipt.get("status"), "block_number": receipt.get("blockNumber"), "log_count": len(receipt.get("logs",[]))} if isinstance(receipt,dict) else {"status":"UNAVAILABLE"}
 mission=Mission("live-nvda-reference",WALLET,MissionState.BORROWED,LOCKED_MARKET_ID,{"requested_debt_atomic":1000000},{"market_state":state,"position":position,"collateral_supply_tx":SUPPLY,"approval_tx":APPROVAL,"borrow_tx":BORROW,"borrow_receipt":receipt_evidence})
 store.save(mission); store.event(mission.id,"REAL_TX_EVIDENCE",{"approval_tx":APPROVAL,"supply_tx":SUPPLY,"borrow_tx":BORROW,"borrow_receipt":receipt_evidence,"position":position}); print(json.dumps({"mission":mission.id,"state":mission.state,"position":position,"market_state":state,"borrow_tx":BORROW,"borrow_receipt":receipt_evidence},indent=2)); store.close()
if __name__=="__main__": main()
