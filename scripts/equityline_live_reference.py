from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.segue_api.mission import Mission, MissionState, MissionStore
from backend.segue_api.morpho import borrower_position, market_state, LOCKED_MARKET_ID

WALLET="0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA"
APPROVAL="0x54851555018424d3d9474fefcfc977fa12950450a0a92762b803a8df1bcfe24d"
SUPPLY="0x934f5a9241ccc429acdc5672427dc46e2d30b940d030b6801336efce357df953"
def main():
 store=MissionStore(); position=borrower_position("https://api.morpho.org",LOCKED_MARKET_ID,WALLET); state=market_state("https://api.morpho.org",LOCKED_MARKET_ID)
 mission=Mission("live-nvda-reference",WALLET,MissionState.BORROWED,LOCKED_MARKET_ID,{"requested_debt_atomic":1000000},{"market_state":state,"position":position,"collateral_supply_tx":SUPPLY,"approval_tx":APPROVAL})
 store.save(mission); store.event(mission.id,"REAL_TX_EVIDENCE",{"approval_tx":APPROVAL,"supply_tx":SUPPLY,"position":position}); print(json.dumps({"mission":mission.id,"state":mission.state,"position":position,"market_state":state},indent=2)); store.close()
if __name__=="__main__": main()
