"""Real HTTP adapter against a synthetic loopback server, with external proxies blocked."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from city_photo.config import Config
from city_photo.vision import Ollama
from city_photo.schemas import Visual
from test_pipeline import synthetic_visual

def test_local_api_ignores_external_proxy(monkeypatch):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def respond(self,value):
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())
        def do_GET(self):
            calls.append(self.path)
            self.respond({'version':'synthetic'} if self.path=='/api/version' else
                         {'models':[{'name':'qwen3-vl:4b-instruct-q4_K_M','digest':'test'}]})
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(self.path)
            if self.path=='/api/show':
                return self.respond({'capabilities':['vision']})
            assert body['stream'] is True and body['think'] is False
            assert len(body['messages'][0]['images'])==1
            assert isinstance(body['format'],dict)
            orientation='clockwise_rotation' in body['format']['properties']
            response=dict(clockwise_rotation=0,certain=True,reason='Synthetic') if orientation else synthetic_visual()
            self.respond({'message':{'content':json.dumps(response)},'done_reason':'stop'})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    monkeypatch.setenv('HTTP_PROXY','http://external.invalid:1')
    monkeypatch.setenv('HTTPS_PROXY','http://external.invalid:1')
    monkeypatch.setenv('NO_PROXY','')
    try:
        backend=Ollama(Config(ollama_url=f'http://127.0.0.1:{server.server_port}'))
        assert backend.identity()['model_digest']=='test'
        assert backend.orientation(b'synthetic')['clockwise_rotation']==0
        raw,_=backend.assess(b'synthetic','Synthetic test')
        Visual.model_validate_json(raw)
        assert calls==['/api/version','/api/tags','/api/show','/api/chat','/api/chat']
    finally:
        server.shutdown()
        server.server_close()
