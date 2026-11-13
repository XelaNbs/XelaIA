import os
from pathlib import Path
import shutil

def subscription_environment(source=None):
    source=dict(os.environ if source is None else source)
    result={k:v for k,v in source.items() if not k.startswith('ANTHROPIC_') and k not in ('CLAUDE_CODE_OAUTH_TOKEN','CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY')}
    entries=[str(Path.home()/'.local/bin'),'/opt/homebrew/bin','/usr/local/bin','/usr/bin','/bin']
    result['PATH']=os.pathsep.join(dict.fromkeys(entries+source.get('PATH','').split(os.pathsep)))
    result['JARVIS_MOTEUR']='claude-code'
    result['JARVIS_MODELE_CC']='sonnet'
    return result

def claude_binary():
    env=subscription_environment()
    binary=shutil.which('claude',path=env['PATH'])
    if not binary:raise RuntimeError('Claude Code introuvable dans ~/.local/bin, /opt/homebrew/bin ou le PATH')
    return binary
