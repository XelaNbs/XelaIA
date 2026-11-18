"""UI projections grouped by offer URL, with evidence attached to each result."""
import json
from integration.receipts import canonical_url

ACTIVE_AGENTS={
 'jobs':{'label':'Recherche emploi','tools':['search_jobs'],'role':'Recherche et préparation ; résultats consultables'},
 'applications':{'label':'Dossiers de candidature','tools':['prepare_application'],'role':'CV et lettres PDF ; dépôt non connecté'},
 'editor':{'label':'Padel · contenus','tools':['padel_plan'],'role':'Scripts et planning ; publication non connectée'},
 'memory':{'label':'Mémoire','tools':['remember'],'role':'Informations conservées et modifiables'},
 'languages':{'label':'Langues','tools':['language_turn'],'role':'Pratique en conversation ; pas de certification'},
}


def project(source):
    groups={};aliases={}
    for offer in source['offers']:
        identity=canonical_url(offer.get('lien')) or offer['key']
        group=groups.setdefault(identity,{'offer':offer,'aliases':[]})
        group['aliases'].append(offer['key'])
        if offer.get('dossier'):group['offer']=offer
    jobs=[]
    for identity,group in groups.items():
        o=group['offer'];key=o['key']
        for alias in group['aliases']:aliases[alias]=key
        group['key']=key
        jobs.append({'id':key,'company':o.get('entreprise',''),'title':o.get('titre',''),'location':o.get('lieu',''),
            'url':o.get('lien',''),'source':o.get('source') or o.get('lien',''),'posted':o.get('date_publication'),
            'checked':o.get('verified_at',0),'score':o.get('score',0),
            'reasons':json.dumps([o.get('pourquoi') or 'Adéquation à relire',o.get('points_faibles') or 'Exigences à vérifier'],ensure_ascii=False),
            'description':o.get('description',''),'missing':json.dumps(['Dépôt non connecté ; aucun accusé de candidature']),
            'state':o.get('statut','trouvée'),'source_status':'unverified','aliases':group['aliases']})
    docs=[]
    for f in source['files']:
        group=groups.get(canonical_url(f.get('offer_url')))
        job_id=group['key'] if group else aliases.get(f.get('offer_key'))
        valid=f.get('validation',{}).get('valid',False) and f.get('available',False)
        docs.append({'id':f['id'],'job_id':job_id,'task_id':f.get('task_id'),'kind':f['kind'],
            'content':'# '+f['name'],'state':'draft' if valid else 'blocked','created':f['created'],
            'filename':f['name'],'sha256':f['sha256'],'size':f['size'],'origin':f['origin'],
            'validation':f['validation'],'available':f.get('available',False)})
    dossiers=[]
    for job in jobs:
        pieces=[d for d in docs if d['job_id']==job['id']]
        chosen={}
        for kind in ('application','cover_letter','offer_brief'):
            candidates=[d for d in pieces if d['kind']==kind and d['state']!='blocked']
            if candidates:chosen[kind]=max(candidates,key=lambda d:(d['origin']=='executed',d['created']))
        dossiers.append({**job,'files':list(chosen.values()),'history':pieces,'state':'draft' if {'application','cover_letter'}.issubset(chosen) else 'needs_documents',
                         'submission':'not_submitted','task_ids':sorted({d['task_id'] for d in pieces if d['task_id']})})
    task_agents={'research':'jobs','application':'applications','padel':'editor'}
    tasks=[]
    for t in source['tasks']:
        tasks.append({'id':t['id'],'agent':task_agents[t['kind']],'kind':t['kind'],'payload':t['payload'],'state':t['state'],
            'attempts':t['attempts'],'max_attempts':3,'created':t['created'],'updated':t['updated'],
            'result':json.dumps(t['result'],ensure_ascii=False),'error':t['error'],'dependency':None,
            'files':[d for d in docs if d['task_id']==t['id']],
            'events':[e for e in source.get('events',[]) if e['task_id']==t['id']]})
    return {'jobs':jobs,'documents':docs,'dossiers':dossiers,'tasks':tasks,'facts':source.get('facts',{}),'agents':ACTIVE_AGENTS}
