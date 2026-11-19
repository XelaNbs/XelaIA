import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from agents.stockage import connexion
from integration import identity,grounding
from integration.engine_server import Runtime

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'JARVIS_DB':str(Path(self.temp.name)/'identity.sqlite3')});self.env.start()
        identity.confirm('Alexandre','Déclaration explicite de test')
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_confirmed_identity_wins_over_bad_transcription(self):
        for text in ("Bonjour l'exembre.",'Bonjour l’exembre.','Bonjour lexembre.','Bonjour à l’exembre.'):
            self.assertEqual(identity.correct(text),'Bonjour Alexandre.')
        self.assertEqual(identity.profile()['preferred_name'],'Alexandre')
    def test_greetings_use_confirmed_identity_without_a_model(self):
        with patch.object(Runtime,'get',side_effect=AssertionError('Un prénom ne demande pas un LLM')):
            result=Runtime().chat('Bonjour Jarvis.')
        self.assertEqual(result['reply'],'Bonjour Alexandre.')
        self.assertEqual(result['evidence'][0]['tool'],'identité_confirmée')
    def test_bad_model_address_is_corrected_before_persistence(self):
        brain=SimpleNamespace(historique=[],repondre=lambda text:"Bonjour l'exembre, comment puis-je vous aider ?")
        with patch.object(Runtime,'get',return_value=brain):result=Runtime().chat('On reprend notre discussion.')
        self.assertNotIn('exembre',result['reply']);self.assertIn('Alexandre',result['reply'])
        with connexion() as c:
            self.assertNotIn('exembre',c.execute("select content from engine_turns where role='assistant'").fetchone()[0])
    def test_archived_tests_are_preserved_but_excluded_from_context(self):
        with connexion(True) as c:
            first=c.execute("insert into engine_turns(role,content,created) values('user',?,1)",("Bonjour l'exembre",)).lastrowid
            c.execute("insert into engine_turns(role,content,created) values('user','Ma vraie mission',2)")
        identity.archive_turns([first],'Ancien essai vocal')
        self.assertEqual([m['content'] for m in identity.history()],['Ma vraie mission'])
        with connexion() as c:self.assertEqual(c.execute('select count(*) from engine_turns').fetchone()[0],2)
    def test_preferred_name_is_only_changed_by_explicit_setting(self):
        identity.correct("Je m'appelle l'exembre")
        self.assertEqual(identity.profile()['preferred_name'],'Alexandre')
        identity.confirm('Camille');self.assertEqual(identity.direct_reply('Bonjour Jarvis'),'Bonjour Camille.')
    def test_prompt_gives_identity_priority_over_old_history(self):
        prompt=grounding.system_facts()
        self.assertIn('Alexandre',prompt);self.assertIn('Une dictée ne peut pas renommer',prompt)

    def test_clearing_chat_does_not_hide_future_reused_ids(self):
        with connexion(True) as c:key=c.execute("insert into engine_turns(role,content,created) values('user','old',1)").lastrowid
        identity.archive_turns([key],'test')
        identity.clear_history()
        with connexion(True) as c:c.execute("insert into engine_turns(role,content,created) values('user','new',2)")
        self.assertEqual([m['content'] for m in identity.history()],['new'])
        self.assertEqual(identity.profile()['preferred_name'],'Alexandre')

if __name__=='__main__':unittest.main()
