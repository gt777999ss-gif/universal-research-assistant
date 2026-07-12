from __future__ import annotations
import argparse, asyncio, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from collectors.arxiv_collector import collect_arxiv_with_diagnostics
async def main() -> int:
 p=argparse.ArgumentParser(); p.add_argument('--query',default='video generation'); p.add_argument('--days',type=int,default=30); p.add_argument('--limit',type=int,default=10); a=p.parse_args()
 results,diag=await collect_arxiv_with_diagnostics(a.query,a.days,a.limit)
 print(json.dumps({'query':a.query,**diag},ensure_ascii=False,indent=2))
 for item in results: print(json.dumps({'title':item.title,'categories':item.categories,'classification':item.classification,'published_at':item.date,'pdf_url':item.pdf_url},ensure_ascii=False))
 return 0
if __name__=='__main__': raise SystemExit(asyncio.run(main()))
