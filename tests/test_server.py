import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from lifecycle import Store
from server import make_handler

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.db.close()
    def test_dashboard_and_state(self):
        with urlopen(self.url) as response: self.assertIn(b'Skill Demo',response.read())
        with urlopen(self.url+'/api/state') as response: self.assertEqual(json.load(response)['skills'],[])
    def test_cross_origin_write_blocked(self):
        request=Request(self.url+'/api/skills',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://example.invalid'})
        with self.assertRaises(HTTPError) as error: urlopen(request)
        self.assertEqual(error.exception.code,403)
    def test_rebinding_host_blocked(self):
        request=Request(self.url+'/api/state',headers={'Host':'evil.invalid'})
        with self.assertRaises(HTTPError) as error: urlopen(request)
        self.assertEqual(error.exception.code,403)

if __name__=='__main__': unittest.main()
