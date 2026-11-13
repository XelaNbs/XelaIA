import contextlib
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = {
    "jarvis": {"label": "JARVIS", "tools": ["queue", "recall"], "role": "Orchestration, priorités et synthèse"},
    "jobs": {"label": "Recherche emploi", "tools": ["search_jobs"], "role": "Sources employeurs, classement et dédoublonnage"},
    "applications": {"label": "Candidatures", "tools": ["prepare_application"], "role": "Documents factuels ; dépôt web non intégré"},
    "contacts": {"label": "Contacts", "tools": ["prepare_contact"], "role": "Coordonnées déclarées et preuves ; aucune adresse déduite"},
    "mail": {"label": "Messagerie", "tools": ["read_mail", "send_batch"], "role": "Lecture Gmail ; envoi uniquement par lot mandaté"},
    "editor": {"label": "Padel · stratégie", "tools": ["padel_plan"], "role": "Ligne éditoriale et calendrier communs"},
    "writer": {"label": "Padel · rédaction", "tools": ["padel_copy"], "role": "Brouillons sans statistiques ni promesses inventées"},
    "visuals": {"label": "Padel · visuels", "tools": [], "role": "Briefs ; montage et publication non connectés"},
    "publisher": {"label": "Padel · diffusion", "tools": [], "role": "Publication bloquée : plateformes non connectées"},
    "analytics": {"label": "Padel · analyse", "tools": [], "role": "Attend des mesures réelles importées"},
    "documents": {"label": "Documents", "tools": ["prepare_document"], "role": "Organisation et modèles ; paiements interdits"},
    "languages": {"label": "Langues", "tools": ["language_turn"], "role": "Anglais, espagnol, portugais ; une question, trois corrections maximum"},
}

def now():
    return time.time()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

class Blocked(Exception):
    pass

class Store:
    def __init__(self, folder=None):
        self.folder = Path(folder or os.environ.get("JARVIS_DATA", ROOT / "data")).resolve()
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.folder / "jarvis.sqlite3"
        self.model_lock = threading.Lock()
        self.stop = threading.Event()
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, category TEXT NOT NULL, content TEXT NOT NULL,
              source TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, agent TEXT, kind TEXT, payload TEXT, state TEXT,
              attempts INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 3, available REAL, created REAL, updated REAL,
              result TEXT, error TEXT, dedupe TEXT UNIQUE, dependency TEXT);
            CREATE TABLE IF NOT EXISTS mandates(id TEXT PRIMARY KEY, title TEXT, policy TEXT, state TEXT, approved REAL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, company TEXT, title TEXT, location TEXT, url TEXT,
              source TEXT, posted TEXT, checked REAL, score INTEGER, reasons TEXT, description TEXT, missing TEXT,
              state TEXT DEFAULT 'new', source_status TEXT DEFAULT 'open');
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, job_id TEXT, kind TEXT, content TEXT, state TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, title TEXT, items TEXT, digest TEXT, state TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, mandate TEXT, agent TEXT, kind TEXT, destination TEXT,
              payload_hash TEXT, state TEXT, receipt TEXT, created REAL, updated REAL, dedupe TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, event TEXT, detail TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY, kind TEXT, interval REAL, next REAL, enabled INTEGER);
            CREATE TABLE IF NOT EXISTS mail(id TEXT PRIMARY KEY, thread TEXT, sender TEXT, subject TEXT, body TEXT,
              partial INTEGER, category TEXT, checked REAL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            ''')
        os.chmod(self.db, 0o600)
        self.config_file = self.folder / "config.json"
        if not self.config_file.exists():
            self.write_config({"model": "claude-code:sonnet", "voice": "Thomas", "voice_provider": "local", "voice_id": "",
                "elevenlabs_enabled": False, "elevenlabs_max_chars": 0, "whisper_model": str(ROOT / "models/ggml-base.bin"),
                "port": 8767, "host": "127.0.0.1", "allowed_hosts": ["127.0.0.1", "localhost"],
                "tls_cert": "", "tls_key": ""})
        token_file = self.folder / "access-token"
        if not token_file.exists():
            token_file.write_text(secrets.token_urlsafe(32))
        os.chmod(token_file, 0o600)
        self.token = token_file.read_text().strip()
        self.seed()

    @contextlib.contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=20)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=20000")
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def config(self):
        return json.loads(self.config_file.read_text())

    def recover(self):
        # Only the single server owner may recover work, never a status CLI.
        with self.connect() as c:
            c.execute("UPDATE tasks SET state='queued', available=?, error='Reprise après interruption' WHERE state='running'", (now(),))

    def write_config(self, config):
        path = self.folder / "config.json"
        tmp = self.folder / "config.tmp"
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(path)

    def audit(self, event, detail):
        with self.connect() as c:
            c.execute("INSERT INTO audit(event,detail,created) VALUES(?,?,?)", (event, json.dumps(detail, ensure_ascii=False), now()))

    def rows(self, query, params=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(query, params).fetchall()]

    def remember(self, category, content, source, status="declared", memory_id=None):
        if status not in ("confirmed", "declared", "to_confirm") or category not in ("profile", "preference", "reference", "language", "legacy"):
            raise ValueError("Catégorie ou statut invalide")
        key = memory_id or secrets.token_hex(10)
        with self.connect() as c:
            c.execute("INSERT INTO memory VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET category=excluded.category,content=excluded.content,source=excluded.source,status=excluded.status,updated=excluded.updated",
                      (key, category, content[:16000], source[:1000], status, now(), now()))
        return key

    def seed(self):
        with self.connect() as c:
            if c.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
                return
            policy = {"objectives": ["Repérer des offres B2B/SaaS orientées relation client"],
                "cities": ["Barcelona", "Lisbon", "Porto", "France"], "roles": ["Account Manager", "Account Executive", "Business Development Manager", "Customer Success Manager", "BDR", "SDR"],
                "criteria": ["Priorité relation client", "Prospection exclusive pénalisée", "Date inconnue signalée"],
                "automatic": ["search_jobs", "rank", "prepare_document", "internal_update"], "max_runs_per_day": 2,
                "max_results": 30, "intervention": ["CV approuvé manquant", "Salaire/langues/droit au travail inconnus", "Envoi externe", "Dépense", "Contrat", "CAPTCHA"]}
            c.execute("INSERT INTO mandates VALUES(?,?,?,?,?)", ("job-pilot", "Recherche emploi · pilote", json.dumps(policy), "active_internal", now()))
            c.execute("INSERT INTO schedules VALUES(?,?,?,?,?)", ("daily-jobs", "search_jobs", 86400, now() + 86400, 1))
            c.execute("INSERT INTO settings VALUES('seeded','1')")
        self.remember("preference", "Vente B2B/SaaS : Barcelone, Lisbonne, Porto, puis France. AM, AE, BDM, CSM ; BDR/SDR si missions adaptées. Privilégier la relation client à la prospection intensive.", "Demande utilisateur du 13/11/2026", "declared", "job-preferences")
        self.remember("reference", "Application : Padel Prog. Aucun chiffre, témoignage ou résultat produit validé à ce stade.", "Demande utilisateur du 13/11/2026", "declared", "padel-reference")

    def enqueue(self, agent, kind, payload=None, dedupe=None, dependency=None):
        if agent not in AGENTS or kind not in AGENTS[agent]["tools"]:
            raise Blocked("Cet agent n’a pas la permission d’utiliser cet outil")
        if kind not in ("search_jobs", "prepare_application", "prepare_contact", "read_mail", "send_batch", "padel_plan", "padel_copy", "prepare_document"):
            raise Blocked("Outil non exécutable en arrière-plan")
        key = secrets.token_hex(10)
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO tasks(id,agent,kind,payload,state,available,created,updated,dedupe,dependency) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (key, agent, kind, json.dumps(payload or {}, ensure_ascii=False), "queued", now(), now(), now(), dedupe or key, dependency))
            row = c.execute("SELECT id FROM tasks WHERE dedupe=?", (dedupe or key,)).fetchone()
        return row[0]

    def claim(self):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE tasks SET state='blocked', error='Dépendance bloquée ou échouée',updated=? WHERE state='queued' AND dependency IN (SELECT id FROM tasks WHERE state IN ('failed','blocked'))", (now(),))
            row = c.execute("SELECT * FROM tasks WHERE state='queued' AND available<=? AND attempts<max_attempts AND (dependency IS NULL OR dependency IN (SELECT id FROM tasks WHERE state='done')) ORDER BY created LIMIT 1", (now(),)).fetchone()
            if row:
                c.execute("UPDATE tasks SET state='running', attempts=attempts+1,updated=? WHERE id=?", (now(), row["id"]))
            return dict(row) if row else None

    def finish(self, task, result=None, error=None, blocked=False):
        state = "done"
        if error:
            state = "blocked" if blocked else ("failed" if task["attempts"] + 1 >= task["max_attempts"] else "queued")
        with self.connect() as c:
            c.execute("UPDATE tasks SET state=?,result=?,error=?,available=?,updated=? WHERE id=?", (state, json.dumps(result, ensure_ascii=False), str(error)[:1000] if error else None, now() + 15 * 2 ** task["attempts"], now(), task["id"]))
        self.audit("task." + state, {"id": task["id"], "kind": task["kind"], "error": str(error) if error else None})

    def document(self, job_id, kind, content, state="draft"):
        key = digest({"job": job_id, "kind": kind})[:24]
        with self.connect() as c:
            c.execute("INSERT INTO documents VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET content=excluded.content,state=excluded.state,created=excluded.created", (key, job_id, kind, content, state, now()))
            c.execute("DELETE FROM documents WHERE job_id IS ? AND kind=? AND id<>?", (job_id,kind,key))
        return key

    def backup(self):
        out = self.folder / "backups"
        out.mkdir(exist_ok=True, mode=0o700)
        path = out / (time.strftime("jarvis-%Y%m%d-%H%M%S-") + secrets.token_hex(3) + ".sqlite3")
        with self.connect() as c:
            dest = sqlite3.connect(path)
            c.backup(dest)
            dest.close()
        os.chmod(path, 0o600)
        self.audit("backup", {"name": path.name})
        return path

def approve_batch(store, batch_id, supplied_digest):
    """Only called from the authenticated human UI/CLI, never an LLM tool."""
    with store.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        batch = c.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not batch or not secrets.compare_digest(batch["digest"], supplied_digest):
            raise Blocked("Lot modifié ou introuvable : relire avant validation")
        items = json.loads(batch["items"])
        if not items or any(not x.get("verified_destination") or not x.get("approved_facts") for x in items):
            raise Blocked("Destinations vérifiées et faits approuvés obligatoires")
        policy = {"batch_id": batch_id, "batch_digest": batch["digest"], "items": items,
            "automatic": ["gmail_send"], "max_per_day": min(5, len(items)), "max_total": len(items),
            "min_interval": 60, "expires": now() + 7 * 86400, "intervention": ["Modification du lot", "Échec ambigu", "Destinataire inconnu", "Dépense", "Contrat"], "sender": items[0].get("sender", "")}
        if not policy["sender"] or any(x.get("sender") != policy["sender"] for x in items):
            raise Blocked("Un unique compte expéditeur vérifié est requis")
        key = "send-" + batch_id
        c.execute("INSERT INTO mandates VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET policy=excluded.policy,state='active',approved=excluded.approved",
            (key, batch["title"], json.dumps(policy), "active", now()))
        c.execute("UPDATE batches SET state='approved' WHERE id=?", (batch_id,))
    store.audit("mandate.approved", {"id": key, "digest": supplied_digest})
    return key

def reserve_send(store, mandate_id, item, agent="mail"):
    if agent != "mail":
        raise Blocked("Seul l’agent messagerie peut envoyer")
    item_hash = digest(item)
    destination = item.get("to", "")
    dedupe = digest({"kind": "gmail_send", "sender": item.get("sender"), "to": destination.casefold(), "job_id": item.get("job_id")})
    with store.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        mandate = c.execute("SELECT * FROM mandates WHERE id=?", (mandate_id,)).fetchone()
        if not mandate or mandate["state"] != "active":
            raise Blocked("Mandat d’envoi actif requis")
        p = json.loads(mandate["policy"])
        if p.get("expires", 0) < now() or "gmail_send" not in p.get("automatic", []):
            raise Blocked("Mandat expiré ou action non couverte")
        if item_hash not in [digest(x) for x in p.get("items", [])] or not item.get("verified_destination") or not item.get("approved_facts"):
            raise Blocked("Contenu ou destination hors mandat")
        if c.execute("SELECT 1 FROM actions WHERE dedupe=?", (dedupe,)).fetchone():
            raise Blocked("Action déjà réservée, confirmée ou incertaine : aucun nouvel envoi")
        history = c.execute("SELECT created FROM actions WHERE mandate=?", (mandate_id,)).fetchall()
        if len(history) >= p["max_total"] or sum(r[0] > now()-86400 for r in history) >= p["max_per_day"]:
            raise Blocked("Limite de volume atteinte")
        if history and now()-max(r[0] for r in history) < p["min_interval"]:
            raise Blocked("Limite de fréquence : attendre avant le prochain envoi")
        # A separate mandate cannot bypass contact frequency limits.
        recent = c.execute("SELECT 1 FROM actions WHERE destination=? AND created>?", (destination.casefold(), now()-7*86400)).fetchone()
        if recent:
            raise Blocked("Destinataire déjà sollicité dans les sept derniers jours")
        key = secrets.token_hex(12)
        c.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?)", (key, mandate_id, agent, "gmail_send", destination.casefold(), item_hash, "reserved", None, now(), now(), dedupe))
        return key
