from __future__ import annotations
import json, os, sys
from urllib.request import Request, urlopen
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NVDA='0xb20000000000000000000078ee7ce2fE4908108C'; API='https://api.morpho.org'; USDC='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
def load_env():
 p=ROOT/'.env'
 if p.exists():
  for l in p.read_text().splitlines():
   if '=' in l and not l.lstrip().startswith('#'):
    k,v=l.split('=',1); os.environ.setdefault(k.strip(),v.strip().strip("'\""))
def get(url):
 with urlopen(Request(url,headers={'accept':'application/json'}),timeout=20) as r:return json.loads(r.read().decode())
def rpc(url,method,params):
 body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
 with urlopen(Request(url,data=body,headers={'content-type':'application/json'}),timeout=20) as r:d=json.loads(r.read().decode())
 if 'error' in d: raise ValueError(d['error'])
 return d['result']
def qualify(m,rpc_url):
 reasons=[]; mid=m['market_id']; oracle=m['oracle_address']
 state=get(f'{API}/v0/blue/markets/8453:{mid}/state').get('data',{}); supply=int(state.get('total_supply_assets',0)); borrow=int(state.get('total_borrow_assets',0)); available=max(0,supply-borrow)
 apy=get(f'{API}/v0/blue/markets/8453:{mid}/apy-averages').get('data',{}); ost=get(f'{API}/v0/oracles/8453:{oracle}/state').get('data',{})
 code=rpc(rpc_url,'eth_getCode',[oracle,'latest']) if rpc_url else '0x'; direct=None; err=None
 if code not in ('0x','0x0'):
  try: direct=int(rpc(rpc_url,'eth_call',[{'to':oracle,'data':'0xa035b1fe'},'latest']),16)
  except Exception as e: err=str(e)
 if m.get('loan_token','').lower()!=USDC.lower(): reasons.append('NON_USDC_LOAN_ASSET')
 if code in ('0x','0x0'): reasons.append('NO_ORACLE_BYTECODE')
 if err: reasons.append('ORACLE_REVERT')
 if not direct: reasons.append('NO_ORACLE_PRICE')
 if not available: reasons.append('ZERO_LIQUIDITY')
 return {'market_id':mid,'loan_token':m.get('loan_token'),'collateral_token':m.get('collateral_token'),'listed':m.get('listed','UNKNOWN'),'oracle':oracle,'irm':m.get('irm_address'),'lltv':m.get('lltv_wad'),'total_supply':supply,'total_borrow':borrow,'available_liquidity':available,'borrow_apy':apy.get('borrow_apy_averages'),'api_oracle_price':ost.get('price'),'oracle_last_updated':ost.get('last_updated_at'),'oracle_last_block':ost.get('last_indexed_block'),'direct_price':direct,'oracle_bytecode':bool(code and code not in ('0x','0x0')),'status':'USABLE' if not reasons else 'REJECTED','reasons':reasons,'direct_error':err}
def main():
 load_env(); rpc_url=os.environ.get('BASE_RPC_URL',''); ms=get(f'{API}/v1/blue/markets?chain_id=8453&collateral_token={NVDA}&limit=100').get('data',[]); rows=[qualify(m,rpc_url) for m in ms]; usable=[r for r in rows if r['status']=='USABLE']; print(json.dumps({'canonical_collateral':NVDA,'markets':rows,'selected_market_id':usable[0]['market_id'] if usable else None},indent=2)); return 0 if usable else 2
if __name__=='__main__': raise SystemExit(main())
