import json
import time
import pytest
from pydantic import ValidationError
from city_photo.config import Config
from city_photo.execution import SystemMemoryPressure
from city_photo.pipeline import analyze
from run_background import failed_photo_ids
from test_pipeline import Fake,workspace,synthetic_visual


def test_three_minute_budget_preserves_regular_default():
    assert Config().photo_deadline_seconds==90
    assert Config(photo_deadline_seconds=180).photo_deadline_seconds==180
    with pytest.raises(ValidationError):
        Config(photo_deadline_seconds=181)


def test_retry_targets_skip_success_and_pending_even_with_changed_model_parameters(workspace):
    store,cfg=workspace
    analyze(store,cfg,backend=Fake(fail=True))
    failed=[r for r in store.rows() if r['status']=='model_error']
    good,bad=failed
    store.update(good['image_id'],status='processed_with_review',visual=synthetic_visual(),cache_key='saved-key',processed_at='saved-time')
    store.update(bad['image_id'],status='manual_review')
    with store.db:
        store.db.execute('INSERT INTO photos(image_id,relative_path,source,sha,metadata,status) VALUES (?,?,?,?,?,?)',
                         ('waiting','waiting.jpg',good['source'],good['sha'],good['metadata'],'pending'))
    saved=dict(store.db.execute('SELECT * FROM photos WHERE image_id=?',(good['image_id'],)).fetchone())
    remaining=failed_photo_ids(store)
    assert remaining=={bad['image_id']}
    cfg=Config.model_validate(cfg.model_dump()|{'photo_deadline_seconds':180,'temperature':.15})
    class Timed(Fake):
        def begin_photo(self,deadline):self.budget=deadline-time.monotonic()
    backend=Timed()
    report=analyze(store,cfg,retry_errors=True,image_ids=remaining,on_photo_done=remaining.discard,backend=backend)
    assert report['processed']==1 and backend.calls==1
    assert 179<backend.budget<=180
    assert remaining==set()
    assert dict(store.db.execute('SELECT * FROM photos WHERE image_id=?',(good['image_id'],)).fetchone())==saved
    assert store.db.execute("SELECT status FROM photos WHERE image_id='waiting'").fetchone()[0]=='pending'
    retried=store.db.execute('SELECT * FROM photos WHERE image_id=?',(bad['image_id'],)).fetchone()
    assert retried['visual']
    assert json.loads(retried['provenance'])['photo_deadline_seconds']==180


def test_memory_recovery_does_not_repeat_already_attempted_failure(workspace):
    store,cfg=workspace
    analyze(store,cfg,backend=Fake(fail=True))
    remaining=failed_photo_ids(store)
    attempted=[]
    def committed(image_id):
        attempted.append(image_id)
        remaining.discard(image_id)
    class LowMemory(Fake):
        def assess(self,*args,**kwargs):
            self.calls+=1
            if self.calls==1:raise RuntimeError('Synthetic model error')
            raise SystemMemoryPressure('Synthetic recovery')
    with pytest.raises(SystemMemoryPressure):
        analyze(store,cfg,retry_errors=True,image_ids=remaining,on_photo_done=committed,backend=LowMemory())
    assert len(attempted)==1 and len(remaining)==1
    saved=store.db.execute('SELECT processed_at FROM photos WHERE image_id=?',(attempted[0],)).fetchone()[0]
    backend=Fake()
    analyze(store,cfg,retry_errors=True,image_ids=remaining,on_photo_done=committed,backend=backend)
    assert backend.calls==1 and not remaining
    assert store.db.execute('SELECT processed_at FROM photos WHERE image_id=?',(attempted[0],)).fetchone()[0]==saved


def test_retry_runner_records_three_minute_mode_without_touching_pending(workspace,tmp_path,monkeypatch):
    import run_background as runner
    store,cfg=workspace
    analyze(store,cfg,backend=Fake(fail=True))
    original=store.db.execute("SELECT * FROM photos WHERE status='model_error' LIMIT 1").fetchone()
    with store.db:
        store.db.execute('INSERT INTO photos(image_id,relative_path,source,sha,metadata,status) VALUES (?,?,?,?,?,?)',
                         ('waiting','waiting.jpg',original['source'],original['sha'],original['metadata'],'pending'))
    class Backend(Fake):
        def cancel_for_memory(self):pass
        def begin_photo(self,deadline):assert 179<deadline-time.monotonic()<=180
    backend=Backend()
    monkeypatch.setattr(runner,'load',lambda _:cfg)
    monkeypatch.setattr(runner,'Ollama',lambda _:backend)
    monkeypatch.setattr('sys.argv',['run_background.py','--workspace',str(store.path),'--output',str(tmp_path/'output'),'--retry-failed-only','--photo-deadline-seconds','180'])
    runner.main()
    state=json.loads((store.path/'analysis_status.json').read_text(encoding='utf-8'))
    assert state['state']=='completed' and state['mode']=='retry_failed'
    assert state['retry_total']==state['retry_completed']==2
    assert state['photo_deadline_seconds']==180
    assert store.db.execute("SELECT status FROM photos WHERE image_id='waiting'").fetchone()[0]=='pending'
