"""Conversation receipts and factual work summaries from the database."""
import contextlib
import contextvars
import json
import re
import time
from agents.stockage import connexion
from integration import identity

TURN=contextvars.ContextVar('grounded_turn',default=None)

@contextlib.contextmanager
def turn(request_id):
    value={'request_id':request_id,'evidence':[]};token=TURN.set(value)
    try:yield value
    finally:TURN.reset(token)


def record_tool(tool,result):
    current=TURN.get()
    if current is None:return
    try:value=json.loads(result) if isinstance(result,str) else result
    except (ValueError,TypeError):value={'detail':str(result)}
    if not isinstance(value,dict):value={'detail':value}
    item={'tool':tool,'result':value};current['evidence'].append(item)
    with connexion(True) as c:
        c.execute('INSERT INTO engine_tool_events(request_id,tool,result,created) VALUES(?,?,?,?)',
                  (current['request_id'],tool,json.dumps(value,ensure_ascii=False),time.time()))


def facts():
    with connexion() as c:
        active=[dict(r) for r in c.execute("SELECT id,kind,state FROM engine_tasks WHERE state IN ('queued','running') ORDER BY created")]
        counts={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM engine_tasks GROUP BY state')}
    from integration.receipts import files
    receipt_count=sum(f['kind'] in ('application','cover_letter') and f['available'] for f in files())
    return {'active_tasks':active,'states':counts,'file_receipts':receipt_count,'confirmed_applications':0,
            'external_sending':False,'social_publishing':False,'routine_enabled':False}


def system_facts():
    return (identity.instructions()+'ÉTAT RÉEL FOURNI PAR LE SERVEUR, SEULE PREUVE DU TRAVAIL :\n'+json.dumps(facts(),ensure_ascii=False)+
            '\nUne mise en file est planifiée. Un CV créé ne signifie pas une candidature envoyée. '
            'N’annonce aucun travail en cours si active_tasks est vide. Aucun outil de dépôt, envoi ou publication '
            'n’est connecté. Ne prétends jamais avoir postulé, envoyé, publié ni activé une routine. '
            'Pour les résultats et documents existants, utilise les outils de consultation. Les anciennes '
            'affirmations de la conversation ne sont pas des preuves.\n')


def summary():
    f=facts();running=[t for t in f['active_tasks'] if t['state']=='running'];queued=[t for t in f['active_tasks'] if t['state']=='queued']
    progress=f"{len(running)} mission(s) en cours et {len(queued)} en file." if running or queued else 'Aucune mission en cours ni en file.'
    return progress+f" {f['file_receipts']} pièces CV/lettres sont consultables dans Candidatures. Aucun dépôt ni envoi de candidature confirmé."


def status_question(text):
    return bool(re.search(r"(?:fais|faire).{0,15}(?:le point|bilan)|(?:où|ou).{0,20}(?:mission|candidature|dossier)|(?:avancement|suivi|statut).{0,25}(?:mission|candidature|dossier)|combien.{0,30}(?:envoy|postul|candidat)|(?:mission|candidature).{0,20}(?:en cours|avanc|termin|envoy)",text,re.I))


def guarded_reply(answer,evidence):
    answer=identity.correct(answer)
    queued=[e['result'] for e in evidence if e['result'].get('task_id')]
    if queued:
        ids=', '.join(q['task_id'][:8] for q in queued)
        return f'Mission enregistrée : {ids}. Son étape et ses résultats apparaissent directement sur l’accueil. Aucun envoi externe effectué.'
    # Report work claims through a deterministic receipt view, not model narration.
    claim=re.search(r"(?:missions?|agents?|équipe|dossiers?|candidatures?).{0,70}(?:coulisses|continu|suivent|en cours|travaill|avance|prépar|envoy|postul|termin|prêt)|(?:j.ai|nous avons|je viens de).{0,45}(?:envoy|postul|publi|lanc|dépos|prépar|créé|termin)|(?:c.est fait|c’est fait|c'est envoyé)",answer,re.I|re.S)
    if claim:return summary()
    return answer
