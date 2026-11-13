import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from integration.environment import subscription_environment, claude_binary
from cerveau import creer_moteur

class BoundaryTests(unittest.TestCase):
    def test_no_api_credentials_and_path_for_launchd(self):
        env=subscription_environment({'PATH':'/usr/bin:/bin','ANTHROPIC_API_KEY':'not-a-real-key','ANTHROPIC_AUTH_TOKEN':'not-a-real-token','JARVIS_MOTEUR':'api'})
        self.assertNotIn('ANTHROPIC_API_KEY',env);self.assertNotIn('ANTHROPIC_AUTH_TOKEN',env)
        self.assertEqual(env['JARVIS_MOTEUR'],'claude-code');self.assertIn(str(Path.home()/'.local/bin'),env['PATH'])
        self.assertEqual(env['JARVIS_MODELE_CC'],'sonnet')
    def test_other_brains_are_explicitly_refused(self):
        for name in ('api','auto','ollama','claude'):
            with patch.dict(os.environ,{'JARVIS_MOTEUR':name}):
                with self.assertRaises(RuntimeError):creer_moteur()
    def test_api_key_refused_inside_engine(self):
        with patch.dict(os.environ,{'JARVIS_MOTEUR':'claude-code','ANTHROPIC_API_KEY':'fake'}):
            with self.assertRaises(RuntimeError):creer_moteur()

if __name__=='__main__':unittest.main()
