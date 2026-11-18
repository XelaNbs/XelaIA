import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from integration import receipts,grounding
from integration.engine_server import Runtime,enqueue,install_dispatch
from integration.presentation import project
from agents.stockage import connexion
from types import SimpleNamespace

class ProofTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.env=patch.dict(os.environ,{'JARVIS_DB':str(self.root/'proof.sqlite3')});self.env.start()
        self.root_patch=patch('integration.receipts.ROOT',self.root);self.root_patch.start()
    def tearDown(self):self.root_patch.stop();self.env.stop();self.temp.cleanup()
    def piece(self,name='CV_test.pdf',body=b'first'):
        file=self.root/'candidatures'/'offer'/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(body);return file
    def test_snapshot_stays_identical_when_original_is_overwritten(self):
        file=self.piece()
        with patch('integration.receipts.validate_generated_pdf',return_value={'pages':1}):saved=receipts.capture(file,'task','offer','https://example.test/job')
        file.write_bytes(b'changed')
        snapshot=self.root/saved['snapshot']
        self.assertEqual(snapshot.read_bytes(),b'first')
        self.assertEqual(receipts.files()[0]['sha256'],hashlib.sha256(b'first').hexdigest())
    def test_tampered_snapshot_is_reported_unavailable(self):
        with patch('integration.receipts.validate_generated_pdf',return_value={}):saved=receipts.capture(self.piece(),'task')
        (self.root/saved['snapshot']).write_bytes(b'tampered')
        self.assertFalse(receipts.files()[0]['available'])
    def test_files_outside_output_folders_are_refused(self):
        file=self.root/'private.pdf';file.write_bytes(b'no')
        with self.assertRaises(ValueError):receipts.capture(file,'task')
    def test_application_cannot_finish_without_cv_and_letter(self):
        task={'id':'task','kind':'application'};current={'errors':[]}
        state,report=receipts.outcome(task,'Le dossier est prêt.',current)
        self.assertNotEqual(state,'done')
        with patch('integration.receipts.validate_generated_pdf',return_value={}):
            receipts.capture(self.piece(),'task','offer');receipts.capture(self.piece('LM_test.pdf'),'task','offer')
        state,report=receipts.outcome(task,'Le dossier est prêt.',current)
        self.assertEqual(state,'done');self.assertIn('Aucun dépôt',report)
    def test_bad_validation_stays_blocked(self):
        with patch('integration.receipts.validate_generated_pdf',side_effect=ValueError('bad numbers')):
            saved=receipts.capture(self.piece(),'task')
        self.assertFalse(saved['validation']['valid'])
        self.assertNotEqual(receipts.outcome({'id':'task','kind':'application'},'Prêt',{'errors':['bad numbers']})[0],'done')
    def test_historical_import_is_explicit_and_idempotent(self):
        self.piece('Fiche_offre.md',b'Historical document')
        receipts.import_history();receipts.import_history()
        files=receipts.files();self.assertEqual(len(files),1);self.assertEqual(files[0]['origin'],'historical_file')
        self.assertIsNone(files[0]['task_id'])
    def test_readonly_summary_does_not_invent_running_jobs(self):
        enqueue('research',{'focus':'Paris'})
        self.assertIn('0 mission(s) en cours et 1 en file',grounding.summary())
        self.assertIn('Aucun dépôt',grounding.summary())
    def test_ungrounded_claim_is_replaced_from_registry(self):
        response=grounding.guarded_reply('Bonjour. Les missions suivent leur cours en coulisses.',[])
        self.assertIn('Aucune mission en cours',response)
        response=grounding.guarded_reply("J’ai envoyé ta candidature.",[])
        self.assertIn('Aucun dépôt',response)
    def test_queue_acknowledgment_comes_from_an_id(self):
        answer=grounding.guarded_reply("J'ai tout terminé",[{'tool':'recherche','result':{'task_id':'1234567890','state':'queued'}}])
        self.assertIn('12345678',answer);self.assertNotIn('terminé',answer)
    def test_status_question_does_not_call_model(self):
        runtime=Runtime()
        with patch.object(runtime,'get',side_effect=AssertionError('model should not run')):
            result=runtime.chat('Fais le point sur les missions et les candidatures.')
        self.assertIn('Aucune mission',result['reply']);self.assertEqual(result['evidence'][0]['tool'],'consulter_registre')
        with connexion() as c:self.assertEqual(c.execute('select count(*) from engine_turn_evidence').fetchone()[0],1)
    def test_normal_conversation_and_memory_evidence_are_kept(self):
        def reply(text):
            grounding.record_tool('memoriser','Mémorisé.');return 'Bonjour Alexandre.'
        brain=SimpleNamespace(repondre=reply,historique=[])
        with patch.object(Runtime,'get',return_value=brain):result=Runtime().chat('Bonjour')
        self.assertEqual(result['reply'],'Bonjour Alexandre.');self.assertEqual(result['evidence'][0]['tool'],'memoriser')
    def test_marking_a_submission_without_confirmation_is_refused(self):
        tool=SimpleNamespace(nom='changer_statut_candidature',fonction=lambda *args:'changed')
        install_dispatch(SimpleNamespace(outils=[tool]))
        self.assertEqual(tool.fonction('Test','candidaté')['state'],'blocked')
    def test_same_url_is_one_dossier_with_linked_cv_and_letter(self):
        offers=[{'key':'one','lien':'https://example.test/job?utm=x','entreprise':'Test','titre':'AM'},
                {'key':'two','lien':'https://example.test/job','entreprise':'Test Inc','titre':'AM'}]
        files=[{'id':str(i),'task_id':'task','path':'file','offer_key':'one','offer_url':'https://example.test/job','kind':kind,
            'validation':{'valid':True},'available':True,'origin':'executed','name':'file.pdf','created':1,'sha256':'hash','size':100} for i,kind in enumerate(('application','cover_letter'))]
        result=project({'offers':offers,'files':files,'tasks':[],'facts':{}})
        self.assertEqual(len(result['dossiers']),1);self.assertEqual(len(result['dossiers'][0]['files']),2)
        self.assertEqual(result['dossiers'][0]['submission'],'not_submitted')

if __name__=='__main__':unittest.main()
