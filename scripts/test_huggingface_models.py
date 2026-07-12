from __future__ import annotations
import argparse,asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from collectors.huggingface_models_collector import collect_huggingface_models_with_diagnostics
async def main():
 p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=30);p.add_argument('--limit',type=int,default=20);a=p.parse_args();r,d=await collect_huggingface_models_with_diagnostics('video',a.days,a.limit);print(json.dumps(d,indent=2));[print(json.dumps({'model':x.model_id,'classification':x.classification,'downloads':x.downloads,'likes':x.likes,'importance':x.importance})) for x in r]
if __name__=='__main__':asyncio.run(main())
