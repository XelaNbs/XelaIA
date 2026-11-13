import ast
import concurrent.futures
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from agents import stockage
from agents import emploi, memoire, missions

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch.dict(os.environ,{'JARVIS_DB':str(Path(self.temp.name)/'test.sqlite3')})
        self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def test_memory_crud(self):
        self.assertEqual(memoire.memoriser('Barcelone en priorité'),'Mémorisé.')
        self.assertIn('Barcelone',memoire.lire_memoire())
        self.assertEqual(memoire.oublier('BARCELONE'),'1 souvenir(s) effacé(s).')
        self.assertEqual(memoire.lire_memoire(),'')
    def test_concurrent_new_offers_do_not_overwrite_each_other(self):
        barrier=threading.Barrier(10)
        def write(i):
            offers=emploi._charger();barrier.wait();offers[str(i)]={'titre':str(i),'statut':'trouvée'};emploi._sauver(offers)
        with concurrent.futures.ThreadPoolExecutor(10) as pool:list(pool.map(write,range(10)))
        self.assertEqual(len(emploi._charger()),10)
    def test_concurrent_field_changes_are_merged(self):
        emploi._sauver({'x':{'titre':'AM','statut':'trouvée','dossier':None}})
        barrier=threading.Barrier(2)
        def write(pair):
            offers=emploi._charger();barrier.wait();offers['x'][pair[0]]=pair[1];emploi._sauver(offers)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:list(pool.map(write,[('statut','entretien'),('dossier','candidatures/test')]))
        self.assertEqual(emploi._charger()['x']['statut'],'entretien')
        self.assertEqual(emploi._charger()['x']['dossier'],'candidatures/test')
    def test_connection_belongs_to_calling_thread(self):
        def own(i):
            with stockage.connexion(True) as c:c.execute('INSERT INTO agent_journal(contenu,created) VALUES(?,?)',(str(i),i))
        with concurrent.futures.ThreadPoolExecutor(6) as pool:list(pool.map(own,range(20)))
        with stockage.connexion() as c:self.assertEqual(c.execute('SELECT count(*) FROM agent_journal').fetchone()[0],20)
    def test_cv_cache_invalidated_by_content(self):
        source=Path(self.temp.name)/'cv.pdf';source.write_bytes(b'%PDF-1 source')
        stockage.sauver_cv({'nom':'Test'},source)
        self.assertEqual(stockage.charger_cv(source),{'nom':'Test'})
        source.write_bytes(b'%PDF-1 changed');self.assertIsNone(stockage.charger_cv(source))
    def test_legacy_import_is_idempotent_and_preserves_files(self):
        root=Path(self.temp.name)/'legacy';(root/'donnees').mkdir(parents=True)
        f=root/'donnees'/'offres.json';f.write_text(json.dumps({'test':{'titre':'AM'}}))
        self.assertTrue(stockage.importer_anciens(root));self.assertFalse(stockage.importer_anciens(root))
        self.assertEqual(emploi._charger()['test']['titre'],'AM');self.assertTrue(f.exists())
    def test_journal_is_persistent(self):
        missions.journaliser('Mission test')
        with stockage.connexion() as c:self.assertEqual(c.execute('SELECT contenu FROM agent_journal').fetchone()[0],'Mission test')
    def test_business_functions_and_signatures_preserved(self):
        allowed={'agents/emploi.py':{'_charger','_sauver','cv_maitre'},'agents/memoire.py':{'memoriser','oublier','lire_memoire','lire_profil'},'agents/missions.py':{'journaliser'}}
        root=Path(__file__).resolve().parents[1]
        for file,changed in allowed.items():
            original=subprocess.check_output(['git','show','97dfdb1:'+file],cwd=root,text=True)
            old={n.name:n for n in ast.parse(original).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
            new={n.name:n for n in ast.parse((root/file).read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
            self.assertEqual(old.keys(),new.keys())
            for name,node in old.items():
                self.assertEqual(ast.dump(node.args),ast.dump(new[name].args),(file,name,'signature'))
                if name not in changed:self.assertEqual(ast.dump(node),ast.dump(new[name]),(file,name,'business logic changed'))

if __name__=='__main__':unittest.main()
