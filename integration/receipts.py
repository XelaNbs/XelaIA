"""Persist real task outputs and immutable copies; never infer an external send."""
from __future__ import annotations
import contextlib
import contextvars
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit, urlunsplit
from agents.stockage import connexion
from integration.document_validation import validate_generated_pdf

ROOT=Path(__file__).resolve().parents[1]
CURRENT=contextvars.ContextVar('mission_receipt',default=None)


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]


def canonical_url(value):
    try:
        p=urlsplit(value or '')
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/').casefold(),'','')) if p.scheme in ('http','https') and p.netloc else ''
    except ValueError:return ''


def event(task_id,phase,detail=None):
    with connexion(True) as c:
        c.execute('INSERT INTO engine_task_events(task_id,phase,detail,created) VALUES(?,?,?,?)',
                  (task_id,phase,json.dumps(detail or {},ensure_ascii=False),time.time()))


@contextlib.contextmanager
def scope(task_id,language=None):
    value={'id':task_id,'language':language,'errors':[],'offers':set()}
    token=CURRENT.set(value)
    try:yield value
    finally:CURRENT.reset(token)


def file_kind(path):
    if path.name.startswith('CV_') and path.suffix.lower()=='.pdf':return 'application'
    if path.name.startswith('LM_') and path.suffix.lower()=='.pdf':return 'cover_letter'
    return 'offer_brief' if path.parent.is_relative_to(ROOT/'candidatures') else 'padel_calendar'


def capture(path,task_id=None,offer_key=None,offer_url=None,origin='executed',language=None):
    path=Path(path).resolve();root=ROOT.resolve()
    if not any(path.is_relative_to(root/folder) for folder in ('candidatures','contenus')):
        raise ValueError('Pièce hors des répertoires autorisés')
    raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest();relative=str(path.relative_to(root))
    key=identity([task_id,relative,sha]);kind=file_kind(path)
    checked={'valid':True,'sha256':sha,'scope':'nonempty_markdown'}
    if path.suffix.lower()=='.pdf':
        try:checked={**validate_generated_pdf(path,language),'valid':True}
        except Exception as error:checked={'valid':False,'error':str(error),'sha256':sha}
    elif not raw.strip():checked={'valid':False,'error':'Document vide','sha256':sha}
    destination=root/'donnees'/'receipts'/key/path.name
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not destination.exists():
        temporary=destination.with_suffix(destination.suffix+'.tmp');temporary.write_bytes(raw)
        temporary.chmod(0o600);os.replace(temporary,destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest()!=sha:raise ValueError('Copie de preuve altérée')
    with connexion(True) as c:
        c.execute('INSERT OR IGNORE INTO engine_task_files VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (key,task_id,relative,str(destination.relative_to(root)),sha,len(raw),kind,offer_key,canonical_url(offer_url),json.dumps(checked,ensure_ascii=False),origin,path.stat().st_mtime))
        if origin=='executed':
            c.execute('INSERT OR REPLACE INTO engine_artifacts VALUES(?,?,?,?)',(relative,int(checked['valid']),json.dumps(checked,ensure_ascii=False),time.time()))
    return {'id':key,'task_id':task_id,'path':relative,'snapshot':str(destination.relative_to(root)),
            'sha256':sha,'size':len(raw),'kind':kind,'offer_key':offer_key,'offer_url':canonical_url(offer_url),
            'validation':checked,'origin':origin,'created':path.stat().st_mtime,'name':path.name}


def install(emploi):
    """Instrument the existing function at the bridge, preserving its workflow."""
    if getattr(emploi.preparer_dossier,'_receipted',False):return
    original=emploi.preparer_dossier
    @functools.wraps(original)
    def wrapped(ia,offre):
        current=CURRENT.get()
        if current is None:return original(ia,offre)
        key=emploi._cle(offre)
        with connexion(True) as c:
            c.execute('INSERT OR REPLACE INTO engine_offer_context VALUES(?,?,?)',(key,json.dumps(offre,ensure_ascii=False),time.time()))
        current['offers'].add(key);event(current['id'],'offer_read',{'offer_key':key,'url':offre.get('lien'),'company':offre.get('entreprise'),'title':offre.get('titre')})
        try:
            relative=original(ia,offre);folder=(ROOT/relative).resolve()
            if not folder.is_relative_to((ROOT/'candidatures').resolve()):raise ValueError('Dossier non autorisé')
            files=[capture(f,current['id'],key,offre.get('lien'),language=current['language']) for f in folder.glob('*') if f.suffix.lower() in ('.pdf','.md')]
            valid={f['kind'] for f in files if f['validation']['valid']}
            if not {'application','cover_letter'}.issubset(valid):raise ValueError('CV ou lettre PDF absent ou non conforme')
            event(current['id'],'dossier_created',{'offer_key':key,'files':[f['id'] for f in files]})
            return relative
        except Exception as error:
            current['errors'].append(str(error));event(current['id'],'dossier_blocked',{'offer_key':key,'reason':str(error)})
            raise
    wrapped._receipted=True;emploi.preparer_dossier=wrapped


def files():
    with connexion() as c:rows=[dict(r) for r in c.execute('SELECT * FROM engine_task_files ORDER BY created DESC')]
    result=[]
    for r in rows:
        path=(ROOT/r['snapshot']).resolve()
        r['name']=Path(r['path']).name;r['validation']=json.loads(r['validation'])
        r['available']=path.is_file() and path.is_relative_to((ROOT/'donnees'/'receipts').resolve())
        if r['available']:r['available']=hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
        result.append(r)
    return result


def outcome(task,report,current):
    output=[f for f in files() if f['task_id']==task['id']]
    valid=[f for f in output if f['available'] and f['validation']['valid']]
    if task['kind']=='padel':
        count=sum(f['kind']=='padel_calendar' for f in valid)
        return ('done',f'{count} fichier de contenu créé. Aucune publication effectuée.') if count else ('blocked','Aucun fichier de contenu vérifiable créé.')
    by_offer={}
    for f in valid:by_offer.setdefault(f['offer_key'],set()).add(f['kind'])
    count=sum({'application','cover_letter'}.issubset(kinds) for kinds in by_offer.values())
    if count:
        state='partial' if current['errors'] else 'done'
        return state,f'{count} dossier(s) créé(s), CV et lettres à relire. Aucun dépôt ni envoi effectué.'
    reason=' ; '.join(current['errors'])
    if not reason and 'a échoué :' in report:reason=report
    if reason:return 'blocked','Aucun dossier complet vérifié. '+reason[:800]
    return 'no_result','Aucun nouveau dossier créé pendant cette mission. Aucun dépôt effectué.'


def import_history():
    """Label reconstructed links as such; they are not past execution receipts."""
    marker='receipts:history:v1'
    with connexion() as c:
        if c.execute('SELECT 1 FROM agent_meta WHERE cle=?',(marker,)).fetchone():return
        tasks=[dict(r) for r in c.execute('SELECT * FROM engine_tasks')]
        offers=[json.loads(r[0])|{'key':r[1]} for r in c.execute('SELECT contenu,cle FROM agent_offres')]
        previous={r['path'].casefold():json.loads(r['report']) for r in c.execute('SELECT * FROM engine_artifacts')}
    for folder in ('candidatures','contenus'):
        for f in (ROOT/folder).rglob('*') if (ROOT/folder).exists() else []:
            if not f.is_file() or f.suffix.lower() not in ('.pdf','.md'):continue
            relative=str(f.relative_to(ROOT));parent=str(f.parent.relative_to(ROOT)).casefold()
            offer=next((o for o in offers if str(o.get('dossier','')).casefold()==parent),{})
            matches=[]
            for t in tasks:
                if not t['created']<=f.stat().st_mtime<=t['updated']+2:continue
                if t['kind']=='application' and offer.get('lien') and offer['lien'] in json.loads(t['payload']).get('offre',''):matches.append(t)
                elif t['kind']=='research' and folder=='candidatures':matches.append(t)
                elif t['kind']=='padel' and folder=='contenus':matches.append(t)
            task_id=matches[0]['id'] if len(matches)==1 else None
            saved=capture(f,task_id,offer.get('key'),offer.get('lien'),origin='reconstructed' if task_id else 'historical_file')
            if previous.get(relative.casefold(),{}).get('error'):
                with connexion(True) as c:
                    check={'valid':False,**previous[relative.casefold()]}
                    c.execute('UPDATE engine_task_files SET validation=? WHERE id=?',(json.dumps(check),saved['id']))
    with connexion(True) as c:c.execute('INSERT OR IGNORE INTO agent_meta VALUES(?,?)',(marker,'done'))
