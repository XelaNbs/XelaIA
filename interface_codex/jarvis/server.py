import base64
import hashlib
import http.cookies
import json
import mimetypes
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .core import AGENTS, ROOT, Blocked, Store, approve_batch, digest, now
from .engine import Engine
from .mail import Gmail, create_batch
from .network import api
from .voice import quota, speak, transcribe

def diagnostics(store):
    config=store.config()
    result={"model":config["model"],"tts":"macOS say (local)","whisper":bool(shutil.which("whisper-cli") and shutil.which("ffmpeg") and Path(config["whisper_model"]).exists()),
        "gmail":(store.folder/"gmail-oauth.json").exists(),"elevenlabs_key":(store.folder/"elevenlabs-key").exists(),
        "social":"non connecté","n8n":"non connecté ; import JSON/CSV disponible","remote_https":bool(config.get("tls_cert")),
        "disk_free_gib":round(shutil.disk_usage(store.folder).free/2**30,1),"voice":config["voice"]}
    try:
        models=api("http://127.0.0.1:11434/api/tags",timeout=3)
        result["ollama"]=True; result["model_installed"]=config["model"] in [m["name"] for m in models.get("models",[])]
    except Exception as e:
        result.update(ollama=False,model_installed=False,model_error=str(e)[:150])
    return result

class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self, address, store):
        self.store=store; self.engine=Engine(store); self.sessions={}; self.login_attempts={}; self.guard=threading.Lock()
        super().__init__(address,Handler)

class Handler(BaseHTTPRequestHandler):
    server_version="Jarvis/0.1"
    def log_message(self, fmt, *args):
        # Never log tokens, request bodies, cookies or URL query strings.
        pass

    def reply(self, value, status=200, content_type="application/json; charset=utf-8", extra=None):
        body=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,(dict,list)) else value
        if isinstance(body,str): body=body.encode()
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Permissions-Policy","microphone=(self), camera=(), geolocation=()")
        if self.server.store.config().get("tls_cert"):
            self.send_header("Strict-Transport-Security","max-age=31536000")
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)

    def check_host(self):
        host=self.headers.get("Host","")
        name=urllib.parse.urlsplit("//"+host).hostname
        if name not in self.server.store.config().get("allowed_hosts",[]):
            raise Blocked("Hôte non autorisé")

    def auth(self):
        self.check_host()
        bearer=self.headers.get("Authorization","")
        if bearer.startswith("Bearer ") and secrets.compare_digest(bearer[7:],self.server.store.token):
            return True
        cookie=http.cookies.SimpleCookie()
        try: cookie.load(self.headers.get("Cookie",""))
        except http.cookies.CookieError: return False
        token=cookie.get("jarvis_pilot_session")
        return bool(token and self.server.sessions.get(token.value,0)>now())

    def read(self, binary=False):
        length=int(self.headers.get("Content-Length","0"))
        if not 0<length<=12_000_000: raise ValueError("Corps vide ou supérieur à 12 Mo")
        raw=self.rfile.read(length)
        return raw if binary else json.loads(raw)

    def do_GET(self):
        try:
            self.check_host()
            path=urllib.parse.urlsplit(self.path).path
            if path=="/api/health": return self.reply({"ok":True,"service":"jarvis"})
            if path.startswith("/api/"):
                if not self.auth(): return self.reply({"error":"Connexion requise"},401)
                store=self.server.store
                if path=="/api/state":
                    result={k:store.rows(q) for k,q in {
                        "memory":"SELECT * FROM memory ORDER BY updated DESC LIMIT 500",
                        "tasks":"SELECT * FROM tasks ORDER BY created DESC LIMIT 100",
                        "mandates":"SELECT * FROM mandates",
                        "jobs":"SELECT * FROM jobs ORDER BY score DESC LIMIT 100",
                        "documents":"SELECT * FROM documents ORDER BY created DESC LIMIT 100",
                        "messages":"SELECT * FROM (SELECT * FROM messages ORDER BY id DESC LIMIT 100) ORDER BY id",
                        "batches":"SELECT * FROM batches ORDER BY created DESC LIMIT 30",
                        "actions":"SELECT * FROM actions ORDER BY created DESC LIMIT 100",
                        "mail":"SELECT * FROM mail ORDER BY checked DESC LIMIT 50",
                        "audit":"SELECT * FROM audit ORDER BY id DESC LIMIT 100",
                        "schedules":"SELECT * FROM schedules"}.items()}
                    result["agents"]=AGENTS
                    result["config"]={k:store.config().get(k) for k in ("model","voice","voice_provider","voice_id","elevenlabs_enabled","elevenlabs_max_chars")}
                    return self.reply(result)
                if path=="/api/diagnostics": return self.reply(diagnostics(store))
                if path.startswith("/api/documents/"):
                    key=path.rsplit("/",1)[1]
                    docs=store.rows("SELECT content FROM documents WHERE id=?",(key,))
                    if not docs: return self.reply({"error":"Document absent"},404)
                    return self.reply(docs[0]["content"],content_type="text/markdown; charset=utf-8",extra={"Content-Disposition":'attachment; filename="jarvis-document.md"'})
                return self.reply({"error":"Route inconnue"},404)
            files={"/":"index.html","/app.js":"app.js","/style.css":"style.css","/manifest.webmanifest":"manifest.webmanifest","/icon.svg":"icon.svg"}
            if path not in files: return self.reply("Introuvable",404,"text/plain")
            file=ROOT/"web"/files[path]
            return self.reply(file.read_bytes(),content_type=mimetypes.guess_type(file)[0] or "application/octet-stream")
        except Blocked as e: self.reply({"error":str(e)},403)
        except Exception as e: self.reply({"error":str(e)[:300]},400)

    def do_POST(self):
        try:
            self.check_host()
            path=urllib.parse.urlsplit(self.path).path
            origin=self.headers.get("Origin")
            scheme="https" if self.server.store.config().get("tls_cert") else "http"
            expected=scheme+"://"+self.headers.get("Host","")
            if origin and origin!=expected: raise Blocked("Origine refusée")
            if path=="/api/login":
                with self.server.guard:
                    ip=self.client_address[0]
                    attempts=[t for t in self.server.login_attempts.get(ip,[]) if t>now()-60]
                    if len(attempts)>=10: return self.reply({"error":"Trop de tentatives : attendre une minute"},429)
                    self.server.login_attempts[ip]=attempts+[now()]
                data=self.read()
                if not secrets.compare_digest(str(data.get("token","")),self.server.store.token):
                    return self.reply({"error":"Clé de connexion incorrecte"},401)
                session=secrets.token_urlsafe(32)
                with self.server.guard:
                    self.server.sessions={k:v for k,v in self.server.sessions.items() if v>now()}
                    self.server.sessions[session]=now()+12*3600
                    self.server.login_attempts.pop(self.client_address[0],None)
                cookie=f"jarvis_pilot_session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200"
                if scheme=="https": cookie+="; Secure"
                return self.reply({"ok":True},extra={"Set-Cookie":cookie})
            if not self.auth(): return self.reply({"error":"Connexion requise"},401)
            if not self.headers.get("Authorization","").startswith("Bearer ") and (origin!=expected or self.headers.get("X-Jarvis-CSRF")!="1"):
                raise Blocked("Protection CSRF : origine et en-tête requis")
            store=self.server.store; engine=self.server.engine
            if path=="/api/transcribe": return self.reply(transcribe(store,self.read(binary=True)))
            if path=="/api/cv":
                raw=self.read(binary=True)
                if not raw.startswith(b"%PDF-"): raise ValueError("Un CV PDF est requis")
                if self.headers.get("X-Approve-Reference")!="yes": raise Blocked("Approbation explicite du CV de référence requise")
                key=hashlib.sha256(raw).hexdigest(); folder=store.folder/"references"; folder.mkdir(exist_ok=True,mode=0o700)
                dest=folder/(key+".pdf"); dest.write_bytes(raw); dest.chmod(0o600)
                store.remember("reference","CV PDF de référence approuvé ; empreinte SHA-256 : "+key,"Import utilisateur via interface","confirmed","approved-cv")
                return self.reply({"cv_sha256":key,"note":"Le PDF est conservé pour pièce jointe. Ses faits ne sont pas extraits automatiquement ; les confirmer dans Mémoire."})
            data=self.read()
            if path=="/api/logout":
                cookie=http.cookies.SimpleCookie(self.headers.get("Cookie","")); current=cookie.get("jarvis_pilot_session")
                if current: self.server.sessions.pop(current.value,None)
                return self.reply({"ok":True},extra={"Set-Cookie":"jarvis_pilot_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            if path=="/api/chat":
                language=data.get("language")
                session="language-"+language if language else "main"
                return self.reply(engine.chat(data.get("text"),session,language,data.get("request_id")))
            if path=="/api/speak":
                audio,mime=speak(store,str(data.get("text","")))
                return self.reply(audio,content_type=mime)
            if path=="/api/tasks":
                return self.reply({"id":store.enqueue(data["agent"],data["kind"],data.get("payload",{}),data.get("dedupe"),data.get("dependency")),"state":"queued"})
            if path=="/api/memory":
                return self.reply({"id":store.remember(data["category"],data["content"],data.get("source","Déclaration via interface"),data.get("status","declared"),data.get("id"))})
            if path=="/api/memory/delete":
                with store.connect() as c: c.execute("DELETE FROM memory WHERE id=?",(data["id"],))
                # Content is deliberately not retained in the audit trail.
                store.audit("memory.deleted",{"id":data["id"]})
                return self.reply({"ok":True,"note":"Supprimé de la mémoire active. Conversations, exports et sauvegardes existants sont distincts."})
            if path=="/api/messages/delete":
                with store.connect() as c: c.execute("DELETE FROM messages")
                return self.reply({"ok":True})
            if path=="/api/import-memory":
                rows=data.get("rows",[])
                if not isinstance(rows,list) or len(rows)>1000: raise ValueError("Liste de 1 000 lignes maximum")
                imported=0
                for row in rows:
                    if not isinstance(row,dict): continue
                    content=row.get("content") or row.get("memory") or row.get("text") or row.get("value")
                    if content is None: content=json.dumps(row,ensure_ascii=False)
                    if not isinstance(content,str): content=json.dumps(content,ensure_ascii=False)
                    key="legacy-"+digest(row)[:20]
                    store.remember("legacy",content,"Import jarvis_memory ; date originale : "+str(row.get("created_at",row.get("date","inconnue"))),"to_confirm",key)
                    imported+=1
                return self.reply({"imported":imported,"status":"to_confirm","tools_executed":0})
            if path=="/api/backup": return self.reply({"filename":store.backup().name,"note":"Sauvegarde SQLite locale, sans clés OAuth. Restauration : serveur arrêté, commande restore."})
            if path=="/api/config":
                config=store.config()
                if "voice" in data:
                    voices=subprocess.run(["/usr/bin/say","-v","?"],capture_output=True,text=True,timeout=10).stdout
                    if data["voice"] not in [line.split("    ")[0].strip() for line in voices.splitlines()] and data["voice"] not in ("Thomas","Daniel","Mónica","Joana"):
                        raise ValueError("Voix locale inconnue")
                    config["voice"]=data["voice"]
                # Optional provider configuration is human-only, no tool can alter it.
                for key in ("voice_provider","voice_id","elevenlabs_enabled","elevenlabs_max_chars"):
                    if key in data: config[key]=data[key]
                if config.get("voice_provider") not in ("local","elevenlabs"): raise ValueError("Fournisseur inconnu")
                config["elevenlabs_max_chars"]=max(0,min(10000,int(config.get("elevenlabs_max_chars",0))))
                store.write_config(config); return self.reply({"ok":True})
            if path=="/api/elevenlabs/quota": return self.reply(quota(store))
            if path=="/api/gmail/profile": return self.reply(Gmail(store).profile())
            if path=="/api/batches": return self.reply(create_batch(store,data["title"],data["items"]))
            if path=="/api/batches/approve":
                mandate=approve_batch(store,data["id"],data["digest"])
                task=store.enqueue("mail","send_batch",{"mandate_id":mandate},dedupe="send-batch-"+mandate)
                return self.reply({"mandate_id":mandate,"task_id":task,"state":"queued"})
            if path=="/api/mandates/pause":
                with store.connect() as c: c.execute("UPDATE mandates SET state='paused' WHERE id=?",(data["id"],))
                store.audit("mandate.paused",{"id":data["id"]}); return self.reply({"ok":True})
            if path=="/api/schedule":
                with store.connect() as c: c.execute("UPDATE schedules SET enabled=? WHERE id='daily-jobs'",(int(bool(data["enabled"])),))
                return self.reply({"ok":True})
            return self.reply({"error":"Route inconnue"},404)
        except Blocked as e: self.reply({"error":str(e),"executed":False},409)
        except (ConnectionError,TimeoutError) as e: self.reply({"error":"Service indisponible : "+str(e)[:200],"executed":False},503)
        except Exception as e: self.reply({"error":str(e)[:500],"executed":False},400)

def serve(store):
    import fcntl
    lock = open(store.folder / '.server.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise Blocked("Un serveur JARVIS utilise déjà cette base")
    config=store.config(); host=config.get("host","127.0.0.1")
    if host not in ("127.0.0.1","localhost") and not (config.get("tls_cert") and config.get("tls_key")):
        raise Blocked("Accès réseau refusé sans certificat et clé HTTPS")
    server=Server((host,int(config.get("port",8765))),store)
    store.recover()
    if config.get("tls_cert"):
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(config["tls_cert"],config["tls_key"]); server.socket=context.wrap_socket(server.socket,server_side=True)
    worker=threading.Thread(target=server.engine.worker,daemon=True,name="jarvis-worker"); worker.start()
    print(f"JARVIS prêt sur {'https' if config.get('tls_cert') else 'http'}://{host}:{server.server_port} — Ctrl+C pour arrêter.",flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        store.stop.set(); server.server_close()
        lock.close()
