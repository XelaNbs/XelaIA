"""SQLite repository only. Connections never cross thread boundaries.

Public agent names, parameters and business workflows are unchanged. A per-thread
snapshot makes a read/modify/save cycle merge only fields changed by that thread.
"""
from __future__ import annotations
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

_local=threading.local()

def db_path():
    return Path(os.environ.get('JARVIS_DB',Path(__file__).resolve().parents[1]/'donnees'/'jarvis.sqlite3')).resolve()

@contextlib.contextmanager
def connexion(write=False):
    path=db_path();path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    c=sqlite3.connect(path,timeout=30);c.row_factory=sqlite3.Row
    try:
        c.execute('PRAGMA busy_timeout=30000');c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS agent_offres(cle TEXT PRIMARY KEY, contenu TEXT NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS agent_memoire(id INTEGER PRIMARY KEY, contenu TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'utilisateur', statut TEXT NOT NULL DEFAULT 'declared');
        CREATE TABLE IF NOT EXISTS agent_cv(id INTEGER PRIMARY KEY CHECK(id=1), contenu TEXT NOT NULL, source TEXT, sha256 TEXT, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS agent_journal(id INTEGER PRIMARY KEY, contenu TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS agent_meta(cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS engine_turns(id INTEGER PRIMARY KEY, role TEXT, content TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS engine_reports(id INTEGER PRIMARY KEY, content TEXT, created REAL, delivered INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS engine_calls(id INTEGER PRIMARY KEY, kind TEXT, result TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS engine_artifacts(path TEXT PRIMARY KEY, valid INTEGER NOT NULL, report TEXT NOT NULL, checked REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS engine_tasks(id TEXT PRIMARY KEY, kind TEXT, payload TEXT, state TEXT, result TEXT, error TEXT, created REAL, updated REAL, attempts INTEGER DEFAULT 0, dedupe TEXT UNIQUE);
        ''')
        if write:c.execute('BEGIN IMMEDIATE')
        yield c
        c.commit()
    except BaseException:
        c.rollback();raise
    finally:
        c.close()
        os.chmod(path,0o600)

def charger_offres():
    with connexion() as c:result={r['cle']:json.loads(r['contenu']) for r in c.execute('SELECT * FROM agent_offres')}
    _local.offres_snapshot=copy.deepcopy(result)
    return result

def sauver_offres(offres):
    before=getattr(_local,'offres_snapshot',{})
    with connexion(True) as c:
        for key,value in offres.items():
            old=before.get(key,{})
            changed={k:v for k,v in value.items() if k not in old or old[k]!=v}
            if not changed and key in before:continue
            row=c.execute('SELECT contenu FROM agent_offres WHERE cle=?',(key,)).fetchone()
            merged=json.loads(row[0]) if row else {}
            merged.update(changed)
            for field in old.keys()-value.keys():merged.pop(field,None)
            c.execute('INSERT INTO agent_offres VALUES(?,?,?) ON CONFLICT(cle) DO UPDATE SET contenu=excluded.contenu,updated=excluded.updated',(key,json.dumps(merged,ensure_ascii=False),time.time()))
        for removed in before.keys()-offres.keys():c.execute('DELETE FROM agent_offres WHERE cle=?',(removed,))
    _local.offres_snapshot=copy.deepcopy(offres)

def lire_memoire(maximum=6000):
    with connexion() as c:rows=c.execute('SELECT date,contenu FROM agent_memoire ORDER BY id').fetchall()
    return ''.join(f'- ({r[0]}) {r[1]}\n' for r in rows)[-maximum:]

def memoriser(information,date):
    with connexion(True) as c:c.execute('INSERT INTO agent_memoire(contenu,date) VALUES(?,?)',(information,date))

def oublier(mot):
    with connexion(True) as c:
        ids=[r[0] for r in c.execute('SELECT id,contenu FROM agent_memoire') if mot.casefold() in r[1].casefold()]
        c.executemany('DELETE FROM agent_memoire WHERE id=?',[(i,) for i in ids])
    return len(ids)

def charger_cv(source=None):
    with connexion() as c:row=c.execute('SELECT * FROM agent_cv WHERE id=1').fetchone()
    if not row:return None
    if source is not None:
        path=Path(source)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:return None
    return json.loads(row['contenu'])

def sauver_cv(cv,source):
    path=Path(source)
    with connexion(True) as c:c.execute('INSERT INTO agent_cv VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET contenu=excluded.contenu,source=excluded.source,sha256=excluded.sha256,updated=excluded.updated',(json.dumps(cv,ensure_ascii=False),str(path),hashlib.sha256(path.read_bytes()).hexdigest(),time.time()))

def journaliser(texte):
    with connexion(True) as c:c.execute('INSERT INTO agent_journal(contenu,created) VALUES(?,?)',(texte,time.time()))

def importer_anciens(root):
    """Idempotent import. Original files are neither removed nor overwritten."""
    root=Path(root);key='legacy-import:'+str(root.resolve())
    with connexion(True) as c:
        if c.execute('SELECT 1 FROM agent_meta WHERE cle=?',(key,)).fetchone():return False
        path=root/'donnees'/'offres.json'
        if path.exists():
            for k,v in json.loads(path.read_text()).items():c.execute('INSERT OR IGNORE INTO agent_offres VALUES(?,?,?)',(k,json.dumps(v,ensure_ascii=False),time.time()))
        path=root/'donnees'/'memoire.md'
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():c.execute("INSERT INTO agent_memoire(contenu,date,source,statut) VALUES(?,?,?,'to_confirm')",(line,'import',str(path)))
        path=root/'donnees'/'cv_maitre.json'
        if path.exists():c.execute('INSERT OR IGNORE INTO agent_cv VALUES(1,?,?,NULL,?)',(path.read_text(),str(path),time.time()))
        path=root/'donnees'/'journal.md'
        if path.exists():c.execute('INSERT INTO agent_journal(contenu,created) VALUES(?,?)',(path.read_text(),time.time()))
        c.execute('INSERT INTO agent_meta VALUES(?,?)',(key,'done'))
    return True
