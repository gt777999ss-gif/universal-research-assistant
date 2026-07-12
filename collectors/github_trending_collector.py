from __future__ import annotations
import asyncio
from datetime import datetime,timedelta,timezone
from typing import Any,Dict,List,Tuple
import httpx
from models import SearchResult
from processors.filter import normalize_text

ENDPOINT='https://api.github.com/search/repositories'; TERMS={'video','diffusion','comfyui','wan','cogvideo','hunyuanvideo','ltx-video','open-sora','motion','world model'}
class GitHubTrendingError(RuntimeError): pass
async def collect_github_trending(query:str,days:int,limit:int,language:str,country:str)->List[SearchResult]:
 r,_=await collect_github_trending_with_diagnostics(query,days,limit);return r
async def collect_github_trending_with_diagnostics(query:str,days:int,limit:int)->Tuple[List[SearchResult],Dict[str,Any]]:
 try:
  data=await fetch(days,limit); parsed=[normalize(x) for x in data]; kept=[x for x in parsed if x and relevant(x)]; kept.sort(key=rank,reverse=True)
  return kept[:limit],{'status':'ok' if kept else 'empty','repositories_parsed':len(data),'relevant_repositories':len(kept),'skipped':len(data)-len(kept),'approach':'official GitHub Search API recent-popularity proxy'}
 except GitHubTrendingError as e:return [],{'status':'failed','reason':str(e)}
async def fetch(days:int,limit:int)->List[Dict[str,Any]]:
 since=(datetime.now(timezone.utc)-timedelta(days=max(days,1))).date().isoformat(); q=f'video pushed:>={since}'
 async with httpx.AsyncClient(headers={'User-Agent':'universal-research-assistant/1.0 (+github-trending-research)','Accept':'application/vnd.github+json'},timeout=15) as c:
  for attempt in range(2):
   try:
    r=await c.get(ENDPOINT,params={'q':q,'sort':'stars','order':'desc','per_page':min(max(limit*3,20),100),'page':1})
    if (r.status_code==429 or r.status_code>=500) and attempt==0:await asyncio.sleep(1);continue
    r.raise_for_status();d=r.json()
    if not isinstance(d,dict) or not isinstance(d.get('items'),list):raise GitHubTrendingError('malformed JSON')
    return d['items']
   except httpx.HTTPStatusError as e:raise GitHubTrendingError('rate limit' if e.response.status_code in {403,429} else f'HTTP {e.response.status_code}') from e
   except httpx.TimeoutException as e:raise GitHubTrendingError('timeout') from e
   except ValueError as e:raise GitHubTrendingError('malformed JSON') from e
 raise GitHubTrendingError('rate limit')
def normalize(x:Dict[str,Any])->SearchResult|None:
 name=str(x.get('full_name') or '');
 if not name:return None
 owner=name.split('/',1)[0];tags=[str(t) for t in x.get('topics',[])];desc=str(x.get('description') or '')
 return SearchResult(source='github_trending',title=name,url=str(x.get('html_url') or f'https://github.com/{name}'),author=owner,date=str(x.get('updated_at') or '') or None,summary=desc,full_text=desc,image_url='',video_url='',repo=name,description=desc,language=str(x.get('language') or ''),stars=int(x.get('stargazers_count') or 0),stars_today=0,topics=tags,updated_at=str(x.get('updated_at') or ''),source_type='github_trending',rationale='Recently active popular repository matched AI-video terms.',reason_selected='Matched official GitHub Search API recent-popularity proxy.',tags=['github_trending',*tags])
def relevant(x:SearchResult)->bool:return any(t in normalize_text(f'{x.repo} {x.description} {x.language} {" ".join(x.topics)}') for t in TERMS)
def rank(x:SearchResult)->Tuple[int,int,float]:return (sum(t in normalize_text(f'{x.repo} {x.description}') for t in TERMS),x.stars,datetime.fromisoformat(x.date.replace('Z','+00:00')).timestamp() if x.date else 0)
