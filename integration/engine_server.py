"""Authenticated loopback API; the sole model is Claude Code/Sonnet.

All business functions remain in the original agents modules. This adapter
serializes conversation state and dispatches their existing functions from a
durable queue. No voice loop, launchd routine, API key or Ollama fallback.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit

from agents import stockage
from integration.environment import subscription_environment,claude_binary

ROOT=Path(__file__).resolve().parents[1]
TOKEN_FILE=ROOT/'donnees'/'bridge-token'
STOP=threading.Event()

def token():
    TOKEN_FILE.parent.mkdir(exist_ok=True,mode=0o700)
    if not TOKEN_FILE.exists():TOKEN_FILE.write_text(secrets.token_urlsafe(32))
    TOKEN_FILE.chmod(0o600)
    return TOKEN_FILE.read_text().strip()

def auth_status():
    try:
        p=subprocess.run([claude_binary(),'auth','status'],capture_output=True,text=True,timeout=15,env=subscription_environment())
        d=json.loads(p.stdout)
        return {'logged_in':bool(d.get('loggedIn')),'auth_method':d.get('authMethod'),'provider':'claude-code','model':'sonnet','api_key_absent':'ANTHROPIC_API_KEY' not in os.environ}
    except Exception as e:return {'logged_in':False,'provider':'claude-code','model':'sonnet','error':str(e)[:200],'api_key_absent':'ANTHROPIC_API_KEY' not in os.environ}

def identifier(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]

def enqueue(kind,payload=None,dedupe=None):
    payload=payload or {}
    if kind not in ('research','application','padel'):raise ValueError('Mission non disponible dans le pilote')
    if kind=='research':payload['nombre']=max(1,min(int(payload.get('nombre',3)),5))
    if kind=='application' and not str(payload.get('offre','')).strip():raise ValueError('Offre précise requise')
    key=secrets.token_hex(12);unique=dedupe or key
    with stockage.connexion(True) as c:
        active=c.execute("SELECT id,payload FROM engine_tasks WHERE kind=? AND state IN ('queued','running') ORDER BY created LIMIT 1",(kind,)).fetchone()
        if active and (json.loads(active['payload'])==payload or (kind=='research' and not payload.get('focus'))):return active['id']
        c.execute('INSERT OR IGNORE INTO engine_tasks(id,kind,payload,state,created,updated,dedupe) VALUES(?,?,?,?,?,?,?)',(key,kind,json.dumps(payload,ensure_ascii=False),'queued',time.time(),time.time(),unique))
        return c.execute('SELECT id FROM engine_tasks WHERE dedupe=?',(unique,)).fetchone()[0]

def install_dispatch(brain):
    """Adapt tool dispatch, never rewrite the agent business functions."""
    for tool in brain.outils:
        if tool.nom=='lancer_recherche_emploi':
            tool.fonction=lambda nombre=5,focus='': 'Mission enregistrée : '+enqueue('research',{'nombre':nombre,'focus':focus})
        elif tool.nom=='preparer_candidature_offre':
            tool.fonction=lambda offre: 'Mission enregistrée : '+enqueue('application',{'offre':offre})
        elif tool.nom=='preparer_contenus_reseaux':
            tool.fonction=lambda nombre=7,theme='': 'Mission enregistrée : '+enqueue('padel',{'nombre':max(1,min(int(nombre),7)),'theme':theme})
        elif tool.nom=='etat_missions':
            tool.fonction=lambda: json.dumps([{'id':t['id'],'kind':t['kind'],'state':t['state']} for t in state()['tasks']],ensure_ascii=False)

class Runtime:
    def __init__(self):self.brain=None;self.chat_lock=threading.RLock();self.init_lock=threading.Lock()
    def get(self):
        if not auth_status().get('logged_in'):raise RuntimeError('Claude Code non connecté. Ouvrir Connecter Claude.command ; aucune API payante ne sera utilisée.')
        with self.init_lock:
            if self.brain is None:
                from cerveau import Cerveau
                self.brain=Cerveau();install_dispatch(self.brain)
                with stockage.connexion() as c:history=c.execute('SELECT role,content FROM engine_turns ORDER BY id DESC LIMIT 24').fetchall()[::-1]
                self.brain.historique=[dict(x) for x in history]
        return self.brain
    def chat(self,text,language=None):
        if not isinstance(text,str) or not text.strip() or len(text)>10000:raise ValueError('Message invalide')
        with self.chat_lock:
            brain=self.get()
            if language:
                if language not in ('anglais','espagnol','portugais'):raise ValueError('Langue inconnue')
                text=f'Exercice en {language}. Pose une seule question, attends la réponse ; trois corrections utiles maximum, sans évaluer la prononciation. Réponse utilisateur : '+text
            answer=brain.repondre(text)
            with stockage.connexion(True) as c:
                for role,content in [('user',text),('assistant',answer)]:c.execute('INSERT INTO engine_turns(role,content,created) VALUES(?,?,?)',(role,content,time.time()))
            return {'reply':answer,'provider':'Claude Code · abonnement','evidence':[]}
    def worker(self):
        with stockage.connexion(True) as c:c.execute("UPDATE engine_tasks SET state='queued',error='Reprise après interruption' WHERE state='running'")
        while not STOP.wait(.5):
            with stockage.connexion(True) as c:
                c.execute("UPDATE engine_tasks SET state='blocked',error='Limite de trois reprises atteinte' WHERE state='queued' AND attempts>=3")
                task=c.execute("SELECT * FROM engine_tasks WHERE state='queued' AND attempts<3 ORDER BY created LIMIT 1").fetchone()
                if task:c.execute("UPDATE engine_tasks SET state='running',attempts=attempts+1,updated=? WHERE id=?",(time.time(),task['id']))
            if not task:continue
            try:
                brain=self.get();p=json.loads(task['payload'])
                from agents import emploi,reseaux,missions
                if task['kind']=='research':result=missions.executer_mission('recherche emploi',lambda:emploi.mission_emploi(brain.moteur,p.get('nombre',3),p.get('focus','')))
                elif task['kind']=='application':result=missions.executer_mission('dossier candidature',lambda:emploi.mission_offre_precise(brain.moteur,p['offre']))
                else:result=missions.executer_mission('contenus réseaux',lambda:reseaux.mission_contenus(brain.moteur,p.get('nombre',3),p.get('theme','')))
                if task['kind'] in ('application','research') and 'a échoué :' not in result:
                    from integration.document_validation import validate_generated_pdf
                    for file in (ROOT/'candidatures').rglob('*.pdf'):
                        if file.stat().st_mtime<task['created']:continue
                        relative=str(file.relative_to(ROOT))
                        try:
                            checked=validate_generated_pdf(file,p.get('expected_language'))
                        except Exception as problem:
                            with stockage.connexion(True) as c:
                                c.execute('INSERT OR REPLACE INTO engine_artifacts VALUES(?,?,?,?)',(relative,0,json.dumps({'error':str(problem)}),time.time()))
                            offers=emploi._charger()
                            for offer in offers.values():
                                if offer.get('dossier')==str(file.parent.relative_to(ROOT)):
                                    offer['statut']='trouvée';offer['validation_error']=str(problem)
                            emploi._sauver(offers)
                            raise
                        with stockage.connexion(True) as c:c.execute('INSERT OR REPLACE INTO engine_artifacts VALUES(?,?,?,?)',(relative,1,json.dumps(checked),time.time()))
                state_='blocked' if 'a échoué :' in result else 'done'
                with stockage.connexion(True) as c:
                    c.execute('UPDATE engine_tasks SET state=?,result=?,updated=? WHERE id=?',(state_,result,time.time(),task['id']))
                    c.execute('INSERT INTO engine_reports(content,created) VALUES(?,?)',(result,time.time()))
            except Exception as e:
                with stockage.connexion(True) as c:c.execute("UPDATE engine_tasks SET state='blocked',error=?,updated=? WHERE id=?",(str(e)[:1200],time.time(),task['id']))

def state():
    with stockage.connexion() as c:
        offers=[{'key':r['cle'],**json.loads(r['contenu'])} for r in c.execute('SELECT * FROM agent_offres')]
        memory=[dict(r) for r in c.execute('SELECT * FROM agent_memoire ORDER BY id DESC LIMIT 500')]
        tasks=[dict(r) for r in c.execute('SELECT * FROM engine_tasks ORDER BY created DESC LIMIT 100')]
        messages=[dict(r) for r in c.execute('SELECT * FROM (SELECT * FROM engine_turns ORDER BY id DESC LIMIT 100) ORDER BY id')]
        reports=[dict(r) for r in c.execute('SELECT * FROM engine_reports ORDER BY id DESC LIMIT 30')]
        validation={r['path']:dict(r) for r in c.execute('SELECT * FROM engine_artifacts')}
    files=[]
    for folder in ('candidatures','contenus'):
        for f in (ROOT/folder).rglob('*') if (ROOT/folder).exists() else []:
            if f.is_file() and f.suffix.lower() in ('.pdf','.md'):
                rel=str(f.relative_to(ROOT));files.append({'id':identifier(rel),'path':rel,'name':f.name,'kind':'application' if folder=='candidatures' else 'padel_calendar','size':f.stat().st_size,'created':f.stat().st_mtime,'validation':validation.get(rel)})
    return {'offers':offers,'memory':memory,'tasks':tasks,'messages':messages,'reports':reports,'files':files}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def respond(self,d,status=200,content_type='application/json; charset=utf-8'):
        b=json.dumps(d,ensure_ascii=False).encode() if isinstance(d,(dict,list)) else d
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
    def allowed(self):
        host=urlsplit('//'+self.headers.get('Host','')).hostname
        return host in ('localhost','127.0.0.1') and secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.token)
    def do_GET(self):
        if not self.allowed():return self.respond({'error':'Authentification locale requise'},401)
        path=urlsplit(self.path).path
        if path=='/health':return self.respond(auth_status())
        if path=='/state':return self.respond(state())
        if path.startswith('/files/'):
            item=next((x for x in state()['files'] if x['id']==path.rsplit('/',1)[-1]),None)
            if not item:return self.respond({'error':'Document absent'},404)
            file=(ROOT/item['path']).resolve()
            if not file.is_relative_to(ROOT/'candidatures') and not file.is_relative_to(ROOT/'contenus'):return self.respond({'error':'Chemin refusé'},403)
            return self.respond(file.read_bytes(),content_type='application/pdf' if file.suffix=='.pdf' else 'text/markdown; charset=utf-8')
        return self.respond({'error':'Route inconnue'},404)
    def do_POST(self):
        if not self.allowed():return self.respond({'error':'Authentification locale requise'},401)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<1000000:raise ValueError('Requête trop volumineuse ou vide')
            d=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
            if path=='/chat':return self.respond(self.server.runtime.chat(d.get('text'),d.get('language')))
            if path=='/tasks':return self.respond({'id':enqueue(d['kind'],d.get('payload'),d.get('dedupe')),'state':'queued'})
            if path=='/memory':
                if d.get('id'):
                    with stockage.connexion(True) as c:c.execute('UPDATE agent_memoire SET contenu=?,source=?,statut=? WHERE id=?',(d['content'],d.get('source','utilisateur'),d.get('status','declared'),int(str(d['id']).removeprefix('m-'))))
                else:
                    from agents.memoire import memoriser
                    memoriser(d['content'])
                return self.respond({'ok':True})
            if path=='/memory/delete':
                with stockage.connexion(True) as c:c.execute('DELETE FROM agent_memoire WHERE id=?',(int(str(d['id']).removeprefix('m-')),))
                return self.respond({'ok':True})
            if path=='/messages/delete':
                with self.server.runtime.chat_lock:
                    with stockage.connexion(True) as c:c.execute('DELETE FROM engine_turns')
                    if self.server.runtime.brain:self.server.runtime.brain.historique=[]
                return self.respond({'ok':True})
            return self.respond({'error':'Action indisponible pendant le pilote'},409)
        except Exception as e:self.respond({'error':str(e)[:1500]},409)

def main():
    if 'ANTHROPIC_API_KEY' in os.environ:raise SystemExit('Clé API interdite dans ce processus')
    if os.environ.get('JARVIS_MOTEUR')!='claude-code':raise SystemExit('Choix explicite claude-code requis')
    import fcntl
    (ROOT/'donnees').mkdir(exist_ok=True,mode=0o700)
    lock=open(ROOT/'donnees'/'engine.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    stockage.importer_anciens(ROOT)
    server=ThreadingHTTPServer(('127.0.0.1',8766),Handler);server.token=token();server.runtime=Runtime()
    threading.Thread(target=server.runtime.worker,daemon=True).start()
    print('Moteur Claude Code/Sonnet sur 127.0.0.1:8766. Routine désactivée dans ce processus.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:STOP.set();server.server_close();lock.close()

if __name__=='__main__':main()
