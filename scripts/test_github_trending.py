from __future__ import annotations
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from collectors.github_trending_collector import collect_github_trending_with_diagnostics
async def main():
 r,d=await collect_github_trending_with_diagnostics('AI video',7,20);print(json.dumps(d,indent=2));[print(json.dumps({'repository':x.repo,'stars':x.stars,'language':x.language,'description':x.summary})) for x in r]
if __name__=='__main__':asyncio.run(main())
