import threading
import pytest
from city_photo.execution import SystemMemoryPressure
from city_photo.memory_guard import MemoryGuard
from city_photo.pipeline import analyze
from test_pipeline import workspace,Fake


def test_low_commit_signals_cancellation():
    cancelled=threading.Event()
    guard=MemoryGuard(cancelled.set,minimum_bytes=100,read=lambda:50)
    guard.start()
    try:
        assert cancelled.wait(2)
    finally:
        guard.close()


def test_cpu_memory_failure_keeps_source_pending(workspace,monkeypatch):
    store,cfg=workspace
    def failed(*args):
        raise MemoryError()
    monkeypatch.setattr('city_photo.execution.prepare_one',failed)
    before=[(r['image_id'],r['status']) for r in store.rows()]
    with pytest.raises(SystemMemoryPressure):
        analyze(store,cfg,limit=1,backend=Fake())
    assert [(r['image_id'],r['status']) for r in store.rows()]==before


def test_guard_can_close_before_start():
    MemoryGuard(lambda:None).close()
