"""Same UI, staging port 8767; original 8765 installation remains untouched."""
import json
import os
from pathlib import Path
import time
import urllib.parse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from jarvis import server
from jarvis.core import Store,AGENTS,Blocked,now
from jarvis.engine import Engine,ROOT_ENGINE

DATA=ROOT_ENGINE/'donnees'
os.environ['JARVIS_DATA']=str(DATA)
BaseHandler=server.Handler
original_get=BaseHandler.do_GET
original_post=BaseHandler.do_POST

def diagnostics(store):
    import shutil
    try:health=Engine(store).call('/health')
    except Exception as e:health={'logged_in':False,'error':str(e)}
    return {'model':'Claude Code · Sonnet','model_installed':bool(health.get('logged_in')),'engine':health,
        'whisper':bool(shutil.which('whisper-cli') and shutil.which('ffmpeg') and Path(store.config()['whisper_model']).exists()),
        'gmail':False,'elevenlabs_key':False,'social':'non connecté','n8n':'import ultérieur','remote_https':False,'voice':store.config().get('voice','Thomas'),
        'pilot':True,'routine':'Seule la programmation existante sur 8765 est active pendant le pilote'}
server.diagnostics=diagnostics

def ui_state(store):
    source=Engine(store).call('/state')
    jobs=[]
    for o in source['offers']:
        jobs.append({'id':o['key'],'company':o.get('entreprise',''),'title':o.get('titre',''),'location':o.get('lieu',''),
            'url':o.get('lien',''),'source':o.get('source') or o.get('lien',''),'posted':o.get('date_publication'),
            'checked':o.get('verified_at',0),'score':o.get('score',0),'reasons':json.dumps([o.get('pourquoi','Résultat du moteur : adéquation à relire'),o.get('points_faibles','Exigences à vérifier')],ensure_ascii=False),
            'description':o.get('description',''),'missing':json.dumps(['Les données proviennent du moteur ; vérifier les preuves de l’offre et le dossier avant dépôt']),
            'state':o.get('statut','trouvée'),'source_status':'unverified'})
    docs=[{'id':f['id'],'job_id':None,'kind':f['kind'],'content':'# '+f['name']+'\n\nFichier créé par le moteur : '+f['path'],'state':'blocked' if f.get('validation') and not f['validation']['valid'] else 'draft','created':f['created'],'filename':f['name']} for f in source['files']]
    memory=[{'id':'m-'+str(m['id']),'category':'reference','content':m['contenu'],'source':m.get('source','utilisateur'),'status':m.get('statut','declared'),'created':0,'updated':0} for m in source['memory']]
    task_agents={'research':'jobs','application':'applications','padel':'editor'}
    tasks=[{'id':t['id'],'agent':task_agents[t['kind']],'kind':t['kind'],'payload':t['payload'],'state':t['state'],'attempts':t['attempts'],'max_attempts':3,'created':t['created'],'result':json.dumps(t['result'],ensure_ascii=False),'error':t['error'],'dependency':None} for t in source['tasks']]
    return {'agents':AGENTS,'memory':memory,'jobs':jobs,'documents':docs,'tasks':tasks,'messages':[{**m,'session':'main'} for m in source['messages']],
        'reports':source['reports'],'batches':[],'actions':[],'mail':[],
        'mandates':store.rows('SELECT * FROM mandates'),'audit':store.rows('SELECT * FROM audit ORDER BY id DESC LIMIT 30'),
        'schedules':[{'id':'daily-jobs','enabled':0}],
        'config':{**{k:store.config().get(k) for k in ('model','voice','voice_provider','voice_id','elevenlabs_enabled','elevenlabs_max_chars')},'pilot':True}}

def get(self):
    path=urllib.parse.urlsplit(self.path).path
    if path=='/api/state' or path.startswith('/api/documents/'):
        try:
            if not self.auth():return self.reply({'error':'Connexion requise'},401)
            if path=='/api/state':return self.reply(ui_state(self.server.store))
            key=path.rsplit('/',1)[1];engine=Engine(self.server.store)
            file=next((f for f in engine.call('/state')['files'] if f['id']==key),None)
            if not file:return self.reply({'error':'Fichier absent'},404)
            return self.reply(engine.call('/files/'+key,binary=True),content_type='application/pdf' if file['name'].endswith('.pdf') else 'text/markdown; charset=utf-8',extra={'Content-Disposition':'inline; filename="'+file['name'].replace('"','')+'"'})
        except Exception as e:return self.reply({'error':str(e)[:600]},409)
    return original_get(self)

def post(self):
    path=urllib.parse.urlsplit(self.path).path
    intercepted={'/api/tasks','/api/memory','/api/memory/delete','/api/messages/delete','/api/schedule','/api/batches','/api/batches/approve','/api/cv','/api/import-memory','/api/gmail/profile'}
    if path not in intercepted:return original_post(self)
    try:
        if not self.auth():return self.reply({'error':'Connexion requise'},401)
        expected='http://'+self.headers.get('Host','')
        if self.headers.get('Origin')!=expected or self.headers.get('X-Jarvis-CSRF')!='1':raise Blocked('Protection CSRF')
        d=self.read();engine=Engine(self.server.store)
        if path=='/api/tasks':return self.reply(engine.enqueue(d['agent'],d['kind'],d.get('payload'),d.get('dedupe')))
        if path in ('/api/memory','/api/memory/delete','/api/messages/delete'):return self.reply(engine.call(path.removeprefix('/api'),d))
        raise Blocked('Pilote isolé : envois et seconde routine désactivés. Le CV maître se prépare dans le moteur.')
    except Exception as e:return self.reply({'error':str(e)[:800]},409)

server.Handler.do_GET=get
server.Handler.do_POST=post

def main():
    store=Store(DATA)
    cfg=store.config();cfg.update(model='claude-code:sonnet',port=8767,host='127.0.0.1',allowed_hosts=['localhost','127.0.0.1'],
        whisper_model=str(ROOT_ENGINE.parent/'jarvis'/'models'/'ggml-base.bin'),voice_provider='local',elevenlabs_enabled=False)
    store.write_config(cfg)
    with store.connect() as c:
        c.execute('UPDATE schedules SET enabled=0')
        # UI memory is a projection of agent_memoire, never a second memory.
        c.execute('DELETE FROM memory')
    server.serve(store)

if __name__=='__main__':main()
