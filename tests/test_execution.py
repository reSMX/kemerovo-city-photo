import json
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from city_photo.config import Config
from city_photo.execution import PhotoDeadlineExceeded, PreparationBuffer
from city_photo.pipeline import analyze
from city_photo.vision import Ollama,TruncatedResponse
from test_pipeline import Fake
from test_pipeline import workspace


def test_stream_deadline_closes_dribbling_server_and_next_request_works():
    disconnected=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(200)
            self.send_header('Content-Type','application/x-ndjson')
            self.end_headers()
            if body['messages'][0]['content']=='slow':
                try:
                    for _ in range(200):
                        self.wfile.write(b'{"message":{"content":" "},"done":false}\n')
                        self.wfile.flush()
                        time.sleep(.02)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                    disconnected.set()
            else:
                self.wfile.write(b'{"message":{"content":"{}"},"done":true,"done_reason":"stop"}\n')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        backend=Ollama(Config(ollama_url=f'http://127.0.0.1:{server.server_port}'))
        backend.begin_photo(time.monotonic()+.25)
        started=time.monotonic()
        with pytest.raises(PhotoDeadlineExceeded):
            backend.chat(b'synthetic','slow',{'type':'object'})
        assert time.monotonic()-started<.8
        assert disconnected.wait(2), 'Client timeout must actually close the remote request'
        backend.end_photo()
        assert backend.chat(b'synthetic','fast',{'type':'object'})[0]=='{}'
    finally:
        server.shutdown()
        server.server_close()


def test_cpu_prepares_next_photo_while_consumer_is_busy(monkeypatch):
    from city_photo.execution import PreparedPhoto
    next_ready=threading.Event()
    def prepare(row,side):
        if row['image_id']=='second': next_ready.set()
        return PreparedPhoto(b'synthetic',.01)
    monkeypatch.setattr('city_photo.execution.prepare_one',prepare)
    buffer=PreparationBuffer([{'image_id':'first'},{'image_id':'second'}],1280,1,2)
    try:
        assert buffer.take('first',time.monotonic()+1).image==b'synthetic'
        assert next_ready.wait(.5)
    finally:
        buffer.close()


def test_execution_settings_do_not_repeat_successful_inference(workspace):
    store,cfg=workspace
    backend=Fake()
    analyze(store,cfg,backend=backend)
    calls=backend.calls
    cfg.photo_deadline_seconds=20.0
    cfg.preprocess_workers=1
    cfg.preprocess_buffer=1
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls==calls


def test_budget_is_shared_across_retries_and_timeout_is_not_retried_on_resume(workspace):
    store,cfg=workspace
    cfg.photo_deadline_seconds=.08
    cfg.retries=1
    class Fails(Fake):
        def assess(self,*args,**kwargs):
            self.calls+=1
            time.sleep(.02)
            raise TruncatedResponse('',{'eval_count':1})
    backend=Fails()
    started=time.monotonic()
    analyze(store,cfg,limit=1,backend=backend)
    assert time.monotonic()-started<.5
    manual=[r for r in store.rows() if r['status']=='manual_review']
    assert len(manual)==1 and not manual[0]['visual']
    saved=manual[0]['processed_at']
    cfg.photo_deadline_seconds=90.0
    analyze(store,cfg,resume=True,backend=Fake())
    assert store.db.execute('SELECT processed_at FROM photos WHERE image_id=?',(manual[0]['image_id'],)).fetchone()[0]==saved
