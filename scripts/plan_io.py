"""Coordinate CLI plan updates with HTML saves on macOS/Linux."""
from contextlib import contextmanager
from pathlib import Path
import fcntl

@contextmanager
def edit_lock(plan):
    with open(str(Path(plan).resolve())+'.edit.lock','a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
