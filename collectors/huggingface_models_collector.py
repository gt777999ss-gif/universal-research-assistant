from __future__ import annotations
import asyncio, logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
import httpx
from models import SearchResult
from processors.filter import normalize_text

LOGGER=logging.getLogger(__name__); ENDPOINT="https://huggingface.co/api/models"; MAX_ATTEMPTS=2
VIDEO_TERMS={"video","text to video","image to video","video diffusion","world model","motion","animation","video editing","wan","cogvideo","hunyuan","skyreels","opensora","ltx","animatediff"}
EXCLUDED={"audio","embedding","dataset","space","llm","language model","image classification"}
class HuggingFaceModelsError(RuntimeError): pass
async def collect_huggingface_models(query:str,days:int,limit:int,language:str,country:str)->List[SearchResult]:
 r,_=await collect_huggingface_models_with_diagnostics(query,days,limit); return r
async def collect_huggingface_models_with_diagnostics(query:str,days:int,limit:int)->Tuple[List[SearchResult],Dict[str,Any]]:
 try:
  payload=await fetch_models(limit); parsed=[normalize_model(x) for x in payload]; kept=[x for x in parsed if x and current(x,days) and relevant(x)]; kept.sort(key=rank,reverse=True)
  return kept[:limit],{"status":"ok" if kept else "empty","models_parsed":len(payload),"relevant_models":len(kept),"skipped":len(payload)-len(kept)}
 except HuggingFaceModelsError as exc: return [],{"status":"failed","reason":str(exc),"models_parsed":0,"relevant_models":0}
async def fetch_models(limit:int)->List[Dict[str,Any]]:
 async with httpx.AsyncClient(headers={"User-Agent":"universal-research-assistant/1.0 (+hf-model-research)","Accept":"application/json"},timeout=httpx.Timeout(15,connect=5,read=10,write=10)) as c:
  for attempt in range(MAX_ATTEMPTS):
   try:
    resp=await c.get(ENDPOINT,params={"search":"video","limit":min(max(limit*3,20),100),"sort":"lastModified","direction":-1,"full":True});
    if (resp.status_code==429 or resp.status_code>=500) and attempt+1<MAX_ATTEMPTS: await asyncio.sleep(1);continue
    resp.raise_for_status(); data=resp.json()
    if not isinstance(data,list): raise HuggingFaceModelsError("malformed JSON")
    return data
   except httpx.HTTPStatusError as e: raise HuggingFaceModelsError("rate limit" if e.response.status_code==429 else f"HTTP {e.response.status_code}") from e
   except httpx.TimeoutException as e:
    if attempt+1<MAX_ATTEMPTS: await asyncio.sleep(1);continue
    raise HuggingFaceModelsError("timeout") from e
   except ValueError as e: raise HuggingFaceModelsError("malformed JSON") from e
 raise HuggingFaceModelsError("rate limit")
def normalize_model(x:Dict[str,Any])->SearchResult|None:
 mid=str(x.get("modelId") or "");
 if not mid:return None
 tags=[str(t) for t in x.get("tags",[])]; text=normalize_text(" ".join([mid,x.get("pipeline_tag") or "",*tags])); classification=classify(text); author=mid.split("/",1)[0] if "/" in mid else ""
 return SearchResult(source="huggingface_models",title=mid,url=f"https://huggingface.co/{mid}",author=author,date=str(x.get("lastModified") or x.get("createdAt") or "") or None,summary=f"Hugging Face model {mid} ({classification}).",full_text="",image_url="",video_url="",model_id=mid,downloads=int(x.get("downloads") or 0),likes=int(x.get("likes") or 0),created_at=str(x.get("createdAt") or ""),last_modified=str(x.get("lastModified") or ""),pipeline_tag=str(x.get("pipeline_tag") or ""),hf_tags=tags,license=str((x.get("cardData") or {}).get("license") or ""),model_url=f"https://huggingface.co/{mid}",paper_url="",github_url="",description="",source_type="huggingface_model",classification=classification,importance=importance(x,text),confidence="high" if "video" in text else "medium",rationale="Matches deterministic AI-video model terms.",reason_selected="Matched Hugging Face AI-video model search.",tags=["huggingface_models",classification,*tags[:10]])
def relevant(x:SearchResult)->bool:
 text=normalize_text(f"{x.model_id} {x.pipeline_tag} {' '.join(x.hf_tags)}")
 return any(t in text for t in VIDEO_TERMS) and not any(t in text for t in EXCLUDED)
def current(x:SearchResult,days:int)->bool:
 try:return datetime.fromisoformat(x.date.replace("Z","+00:00"))>=datetime.now(timezone.utc)-timedelta(days=days)
 except (ValueError,AttributeError):return True
def classify(t:str)->str:
 if "image to video" in t:return "image_to_video"
 if "text to video" in t:return "text_to_video"
 if "editing" in t:return "video_editing"
 if "motion" in t or "animate" in t:return "motion"
 if "avatar" in t:return "avatar"
 if "world model" in t:return "world_model"
 if "lora" in t:return "video_lora"
 return "video_generation" if "video" in t else "other"
def importance(x:Dict[str,Any],t:str)->str:
 score=(int(x.get("downloads") or 0)>100000)+(int(x.get("likes") or 0)>500)+(any(k in t for k in {"wan","cogvideo","hunyuan","ltx","opensora"}))
 return "critical" if score>=3 else "high" if score>=2 else "medium" if score else "low"
def rank(x:SearchResult)->Tuple[int,int,int,float]:
 return ({"critical":4,"high":3,"medium":2,"low":1}.get(x.importance,0),x.downloads,x.likes,datetime.fromisoformat(x.date.replace("Z","+00:00")).timestamp() if x.date else 0)
