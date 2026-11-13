"""Copy approved inputs; never mutate the installation on port 8765."""
from pathlib import Path
import json
import shutil
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents import stockage

ROOT=Path(__file__).resolve().parents[1]
def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--cv',type=Path);args=parser.parse_args()
    source=args.cv or ROOT/'mon_cv.pdf'
    if not source.exists():raise SystemExit('CV MASTER de référence introuvable')
    target=ROOT/'mon_cv.pdf'
    if not target.exists():shutil.copyfile(source,target);target.chmod(0o600)
    old=ROOT.parent/'jarvis'/'data'/'jarvis.sqlite3'
    c=sqlite3.connect(f'file:{old}?mode=ro',uri=True);c.row_factory=sqlite3.Row
    profile=c.execute("SELECT content,source,status FROM memory WHERE category IN ('profile','preference','reference') ORDER BY updated").fetchall()
    notes='\n\n'.join(r['content']+'\nSource : '+r['source']+' ; statut : '+r['status'] for r in profile)
    p=ROOT/'profil.md'
    if not p.exists():p.write_text(notes);p.chmod(0o600)
    with stockage.connexion(True) as db:
        if not db.execute("SELECT 1 FROM agent_meta WHERE cle='codex-profile-import'").fetchone():
            for r in profile:db.execute('INSERT INTO agent_memoire(contenu,date,source,statut) VALUES(?,?,?,?)',(r['content'],'13/11/2026',r['source'],r['status']))
            db.execute("INSERT INTO agent_meta VALUES('codex-profile-import','done')")
    c.close()
    print('CV de référence et profil copiés dans la branche isolée ; données originales inchangées.')
if __name__=='__main__':main()
