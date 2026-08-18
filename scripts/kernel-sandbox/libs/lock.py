"""
file locking for kernel-sandbox.

Why this exists: guard the artifacts/cache directory read-check-write sequence
against races between concurrent invocations targeting the same commit/arch/config
as well the rpm_build_root
"""
import contextlib
import fcntl
import time
from pathlib import Path
from libs.console import get_logger
from libs.errors import KernelSandboxError

logger = get_logger(__name__)


class LockTimeoutError(KernelSandboxError):
    pass


@contextlib.contextmanager
def file_lock(lock_path, description="<operation>", timeout=None, poll_interval=2):
    """
    Derived(partially) from kbuild/python/kbuild/utils.py (kbuild.utils.LockedFile)
    - you can provide a description of the lock operation
    - if no timeout is specified, then the second waits can happen until first lock unfolds
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as fh:
        acquired = False
        start = time.monotonic()
        logged_wait = False

        while not acquired:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                if not logged_wait:
                    logger.info(
                        f"Waiting for exclusive lock before {description} (another kernel-sandbox "
                        f"invocation appears to be using {lock_path})..."
                    )
                    logged_wait = True
                if timeout is not None and (time.monotonic() - start) > timeout:
                    raise LockTimeoutError(
                        f"Timed out after {timeout}s waiting for lock on {lock_path} ({description})"
                    )
                time.sleep(poll_interval)

        if logged_wait:
            logger.info(f"Lock acquired for {description}.")

        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
