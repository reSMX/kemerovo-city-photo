"""Bounded CPU look-ahead and a shared wall-clock deadline for each photo."""
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from .metadata import sha_file, prepare


class PhotoDeadlineExceeded(TimeoutError):
    def __init__(self, raw=None):
        super().__init__('Photo wall-clock budget exhausted; reserved for manual review')
        self.raw=raw


def remaining(deadline):
    value=deadline-time.monotonic()
    if value<=0:
        raise PhotoDeadlineExceeded()
    return value


@dataclass(frozen=True)
class PreparedPhoto:
    image: bytes
    cpu_seconds: float


def prepare_one(row,long_side):
    started=time.monotonic()
    path=Path(row['source'])
    before=path.stat()
    if sha_file(path)!=row['sha']:
        raise ValueError('Source changed: import again')
    image=prepare(path,long_side)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('Source changed during preprocessing: import again')
    return PreparedPhoto(image,time.monotonic()-started)


class PreparationBuffer:
    def __init__(self,rows,long_side,workers=2,depth=4):
        self.rows=iter(rows)
        self.side=long_side
        self.depth=depth
        self.pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='photo-cpu')
        self.pending={}
        self._fill()

    def _fill(self):
        while len(self.pending)<self.depth:
            row=next(self.rows,None)
            if row is None:
                break
            self.pending[row['image_id']]=self.pool.submit(prepare_one,dict(row),self.side)

    def take(self,image_id,deadline):
        future=self.pending.pop(image_id)
        self._fill()
        try:
            return future.result(timeout=remaining(deadline))
        except FutureTimeout as e:
            raise PhotoDeadlineExceeded() from e

    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True)

    def discard(self,image_id):
        future=self.pending.pop(image_id,None)
        if future:
            future.cancel()
        self._fill()

    def rotated(self,row,long_side,rotation,deadline):
        future=self.pool.submit(prepare,row['source'],long_side,rotation)
        try:
            return future.result(timeout=remaining(deadline))
        except FutureTimeout as e:
            raise PhotoDeadlineExceeded() from e
