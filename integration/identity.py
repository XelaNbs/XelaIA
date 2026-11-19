"""Confirmed identity has priority over speech recognition and old conversations."""
import json
import re
import time
from agents.stockage import connexion

KEY='identity:preferred_name'
BAD_NAME=re.compile(r"(?:\bl['’]\s*)?(?:\bexembre\b|\balexembre\b|\blexembre\b)",re.I)


def profile():
    with connexion() as c:
        row=c.execute('SELECT valeur FROM agent_meta WHERE cle=?',(KEY,)).fetchone()
        if row:return json.loads(row[0])
        cached=c.execute('SELECT contenu FROM agent_cv WHERE id=1').fetchone()
    name=(json.loads(cached[0]).get('nom','').split() or [''])[0] if cached else ''
    return {'preferred_name':name,'source':'CV de référence' if name else 'non renseigné'}


def confirm(name,source='Réglage confirmé dans l’interface'):
    name=name.strip()
    if not 1<=len(name)<=60 or not all(c.isalpha() or c in " -’'" for c in name):raise ValueError('Prénom invalide')
    value={'preferred_name':name,'source':source,'updated':time.time()}
    with connexion(True) as c:
        c.execute('INSERT INTO agent_meta VALUES(?,?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur',(KEY,json.dumps(value,ensure_ascii=False)))
    return value


def correct(text):
    name=profile()['preferred_name']
    if not name:return text
    text=BAD_NAME.sub(name,str(text))
    return re.sub(r'\b(Bonjour|Bonsoir|Salut)\s+[àa]\s+'+re.escape(name)+r'\b',lambda m:m.group(1)+' '+name,text,flags=re.I)


def direct_reply(text):
    name=profile()['preferred_name']
    if not name:return None
    if re.fullmatch(r"\s*(bonjour|bonsoir|salut|coucou|hello)(?:\s+jarvis)?[\s.!?,]*",text,re.I):
        greeting='Bonsoir' if text.strip().casefold().startswith('bonsoir') else 'Bonjour'
        return greeting+' '+name+'.'
    if re.search(r"comment\s+je\s+m.appelle|quel\s+est\s+mon\s+prénom|tu\s+connais\s+mon\s+prénom",text,re.I):
        return 'Votre prénom d’usage est '+name+'.'
    return None


def instructions():
    return ('IDENTITÉ CONFIRMÉE PAR L’UTILISATEUR : '+json.dumps(profile(),ensure_ascii=False)+
            '\nCe prénom a priorité sur la transcription, les souvenirs et les anciennes réponses. '
            'Une dictée ne peut pas renommer l’utilisateur. Si vous utilisez son prénom, recopiez '
            'exactement preferred_name. En cas de transcription incohérente, utilisez ce prénom confirmé '
            'ou ne prononcez aucun prénom. Les modifications passent par le réglage d’identité explicite.\n')


def archive_turns(ids,reason):
    with connexion(True) as c:
        c.executemany('INSERT OR REPLACE INTO engine_turn_flags VALUES(?,1,?,?)',[(int(i),reason,time.time()) for i in ids])


def history(limit=100):
    with connexion() as c:
        return [dict(r) for r in c.execute('''SELECT * FROM (
            SELECT t.* FROM engine_turns t WHERE NOT EXISTS (
              SELECT 1 FROM engine_turn_flags f WHERE f.turn_id=t.id AND f.excluded_from_context=1)
            ORDER BY t.id DESC LIMIT ?) ORDER BY id''',(limit,))]


def clear_history():
    with connexion(True) as c:
        c.execute('DELETE FROM engine_turn_evidence')
        c.execute('DELETE FROM engine_turn_flags')
        c.execute('DELETE FROM engine_turns')
