from pathlib import Path
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integration.environment import subscription_environment

ROOT=Path(__file__).resolve().parents[1]
def running(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1):return True
    except Exception:return False
def engine_running():
    token_file=ROOT/'donnees'/'bridge-token'
    if not token_file.exists():return False
    try:
        req=urllib.request.Request('http://127.0.0.1:8766/health',headers={'Authorization':'Bearer '+token_file.read_text().strip()})
        with urllib.request.urlopen(req,timeout=15):return True
    except Exception:return False
def main():
    private=ROOT/'donnees';private.mkdir(exist_ok=True,mode=0o700)
    py=str(ROOT/'.venv'/'bin'/'python')
    env=subscription_environment();env['JARVIS_DB']=str(private/'jarvis.sqlite3')
    if not engine_running():
        log=open(private/'engine.log','ab');subprocess.Popen([py,'-m','integration.launch_engine'],cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True);log.close()
        for _ in range(30):
            if engine_running():break
            time.sleep(.3)
        else:raise SystemExit('Moteur 8766 non démarré ; consulter donnees/engine.log')
    if not running(8767):
        log=open(private/'interface.log','ab');subprocess.Popen([py,'run_ui.py'],cwd=ROOT/'interface_codex',env=env,stdout=log,stderr=log,start_new_session=True);log.close()
        for _ in range(30):
            if running(8767):break
            time.sleep(.3)
        else:raise SystemExit('Interface 8767 non démarrée ; consulter donnees/interface.log')
    token=(private/'access-token').read_text().strip()
    webbrowser.open('http://localhost:8767/#token='+token)
    print('Pilote ouvert sur localhost:8767 ; original 8765 inchangé. Modèle unique : Claude Code/Sonnet.')
if __name__=='__main__':main()
