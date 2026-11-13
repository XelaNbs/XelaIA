import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from integration.engine_server import Handler,enqueue,state
from agents.stockage import connexion

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patch=patch.dict(os.environ,{'JARVIS_DB':str(Path(self.temp.name)/'db.sqlite3')});self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def test_repeated_generic_search_joins_active_mission(self):
        first=enqueue('research',{'nombre':5,'focus':'Lisbonne'})
        self.assertEqual(enqueue('research',{'nombre':3}),first)
        self.assertEqual(len(state()['tasks']),1)
    def test_nonexistent_tool_is_refused(self):
        with self.assertRaises(ValueError):enqueue('send_email',{})
        with self.assertRaises(ValueError):enqueue('application',{})
    def test_api_requires_auth_and_restricts_host(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.token='test-only-token';server.runtime=None
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/state'
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url)
            req=urllib.request.Request(url,headers={'Authorization':'Bearer test-only-token'})
            self.assertEqual(json.load(urllib.request.urlopen(req))['offers'],[])
            req=urllib.request.Request(url,headers={'Authorization':'Bearer test-only-token','Host':'evil.test'})
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
