"""Resumable single-GPU runner with periodic CSV export, a lock and a stop file."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from city_photo.config import Config,load
from city_photo.storage import Store,now
from city_photo.pipeline import analyze,diagnostic
from city_photo.export import export_all
from city_photo.vision import Ollama
from city_photo.execution import SystemMemoryPressure
from city_photo.memory_guard import MemoryGuard, available_commit_bytes


@contextmanager
def exclusive_workspace(path):
    path=Path(path)
    path.mkdir(parents=True,exist_ok=True)
    handle=(path/'analysis.lock').open('a+b')
    if handle.tell()==0:
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('This workspace already has an active analysis process')
    try:
        yield
    finally:
        handle.seek(0)
        if os.name=='nt':
            msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:
            fcntl.flock(handle,fcntl.LOCK_UN)
        handle.close()


def failed_photo_ids(store):
    """Only model failures with no saved result; never pending or assessed rows."""
    return {row[0] for row in store.db.execute("SELECT image_id FROM photos WHERE status IN ('model_error','manual_review') AND (visual IS NULL OR visual='')")}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='config.full.yaml')
    parser.add_argument('--workspace',default='work')
    parser.add_argument('--output',default='output')
    parser.add_argument('--retry-failed-only',action='store_true',help='Retry only model errors and timeouts without a saved result')
    parser.add_argument('--photo-deadline-seconds',type=float,help='Override total time per photo (maximum 180 seconds)')
    parser.add_argument('--memory-guard',action=argparse.BooleanOptionalAction,default=False,
                        help='Stop when Windows commit reserve is low (disabled by default)')
    args=parser.parse_args()
    cfg=load(args.config)
    if args.photo_deadline_seconds is not None:
        cfg=Config.model_validate(cfg.model_dump() | {'photo_deadline_seconds':args.photo_deadline_seconds})
    workspace=Path(args.workspace).resolve()
    with exclusive_workspace(workspace):
        store=Store(workspace)
        retry_targets=failed_photo_ids(store) if args.retry_failed_only else None
        retry_total=len(retry_targets) if retry_targets is not None else None
        stop=workspace/'stop.request'
        stop.unlink(missing_ok=True)
        status=dict(pid=os.getpid(),started_at=now(),state='running',config=str(Path(args.config).resolve()),
                    memory_guard_enabled=args.memory_guard,photo_deadline_seconds=cfg.photo_deadline_seconds,
                    mode='retry_failed' if args.retry_failed_only else 'all')
        if args.retry_failed_only:
            status.update(retry_total=retry_total,retry_completed=0)
            print(f'Retry mode: {retry_total} failed photos; {cfg.photo_deadline_seconds:g} seconds per photo.',flush=True)
        last_export=0.0
        backend=Ollama(cfg)
        guard=MemoryGuard(backend.cancel_for_memory)
        recoveries=0
        total_recoveries=0
        def photo_done(image_id):
            if retry_targets is not None:
                retry_targets.discard(image_id)
                status['retry_completed']=retry_total-len(retry_targets)
        def unload():
            guard.paused=True
            try:
                backend.request('/api/generate',{'model':cfg.model,'keep_alive':0})
                # Windows releases committed runner memory shortly after the unload reply.
                release_deadline=time.monotonic()+10
                while time.monotonic()<release_deadline:
                    reserve=available_commit_bytes()
                    if reserve is None or reserve>=5*1024**3:
                        break
                    time.sleep(.25)
            finally:
                guard.paused=False
        def publish():
            status.update(updated_at=now(),statuses=dict(store.db.execute('SELECT status,count(*) FROM photos GROUP BY status').fetchall()))
            tmp=workspace/'analysis_status.json.tmp'
            tmp.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
            tmp.replace(workspace/'analysis_status.json')
        def checkpoint(done):
            nonlocal last_export,recoveries
            recoveries=0
            publish()
            if done%10==0 or time.monotonic()-last_export>=60:
                try:
                    export_all(store,cfg,args.output)
                    last_export=time.monotonic()
                except OSError as e:
                    print(f'CSV export deferred: {type(e).__name__}',flush=True)
            if stop.exists():
                raise KeyboardInterrupt()
            reserve=available_commit_bytes() if args.memory_guard else None
            if done%20==0 or (reserve is not None and reserve<5*1024**3):
                print('Recycling Ollama runner to release accumulated host memory.',flush=True)
                unload()
                backend.memory_abort.clear()
        awake=False
        try:
            if os.name=='nt':
                import ctypes
                awake=bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
            publish()
            if args.memory_guard:
                guard.start()
            reserve=available_commit_bytes() if args.memory_guard else None
            if reserve is not None and reserve<5*1024**3:
                unload()
            # Recompute all saved photo scores with current rules; no vision call here.
            export_all(store,cfg,args.output)
            last_export=time.monotonic()
            while True:
                try:
                    if retry_targets is not None and not retry_targets:
                        report={'processed':status['retry_completed'],'no_remaining_failures':True}
                        break
                    report=analyze(store,cfg,resume=True,retry_errors=args.retry_failed_only,
                                   image_ids=retry_targets,on_photo_done=photo_done,on_progress=checkpoint,backend=backend)
                    break
                except SystemMemoryPressure:
                    recoveries+=1
                    total_recoveries+=1
                    status.update(memory_recoveries=total_recoveries,consecutive_memory_recoveries=recoveries)
                    print('Memory reserve low: unloading model; saved photos retained.',flush=True)
                    unload()
                    reserve=available_commit_bytes() if args.memory_guard else None
                    if recoveries>3 or (reserve is not None and reserve<4*1024**3):
                        raise RuntimeError('Stopped for memory reserve; close other memory-heavy programs before resuming')
                    backend.memory_abort.clear()
            status.update(state='completed',report=report)
        except KeyboardInterrupt:
            status['state']='stopped'
            print('Stopped; committed photos remain saved.',flush=True)
        except Exception as e:
            status.update(state='error',error=diagnostic(e))
            print(diagnostic(e),flush=True)
            raise
        finally:
            guard.close()
            try:
                export_all(store,cfg,args.output)
            finally:
                publish()
                store.db.close()
                if awake:
                    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__=='__main__':
    main()
