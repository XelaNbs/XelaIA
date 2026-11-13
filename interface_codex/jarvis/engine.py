"""HTTP client for the sole Claude Code engine. No local LLM/orchestrator."""
import json
from pathlib import Path
import urllib.error
from .network import api,request
from .core import Blocked

ROOT_ENGINE=Path(__file__).resolve().parents[2]

class Engine:
    def __init__(self,store):self.store=store
    def call(self,path,data=None,binary=False):
        secret=ROOT_ENGINE/'donnees'/'bridge-token'
        if not secret.exists():raise Blocked('Moteur 8766 arrêté : lancer le pilote isolé')
        headers={'Authorization':'Bearer '+secret.read_text().strip()}
        try:
            if binary:return request('http://127.0.0.1:8766'+path,headers=headers,timeout=30)
            return api('http://127.0.0.1:8766'+path,data,headers,timeout=900)
        except urllib.error.HTTPError as e:
            try:message=json.loads(e.read()).get('error',str(e))
            except Exception:message=str(e)
            raise Blocked(message) from e
    def chat(self,text,session='main',language=None,request_id=None):return self.call('/chat',{'text':text,'language':language,'request_id':request_id})
    def enqueue(self,agent,kind,payload=None,dedupe=None):
        payload=payload or {}
        if kind=='search_jobs':return self.call('/tasks',{'kind':'research','payload':{'nombre':3},'dedupe':dedupe})
        if kind=='prepare_application':
            offers=self.call('/state')['offers'];job=next((x for x in offers if x['key']==payload.get('job_id')),None)
            if not job:raise Blocked('Offre introuvable')
            return self.call('/tasks',{'kind':'application','payload':{'offre':job.get('lien') or json.dumps(job,ensure_ascii=False)},'dedupe':dedupe})
        if kind in ('padel_plan','padel_copy'):return self.call('/tasks',{'kind':'padel','payload':{'nombre':3},'dedupe':dedupe})
        raise Blocked('Cet outil reste désactivé pendant le pilote. Aucun envoi externe.')
    def worker(self):
        # The existing 8765 scheduler is the only routine during this pilot.
        # All new missions are dispatched by the engine's durable worker.
        self.store.stop.wait()
