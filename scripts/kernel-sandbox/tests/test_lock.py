import tempfile
import threading
import time
import unittest
from pathlib import Path

from libs.lock import LockTimeoutError, file_lock


class TestFileLock(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.tmp_dir.name) / "locks" / "test.lock"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_creates_parent_directory(self):
        self.assertFalse(self.lock_path.parent.exists())
        with file_lock(self.lock_path):
            pass
        self.assertTrue(self.lock_path.exists())

    def test_sequential_reacquisition_does_not_hang(self):
        with file_lock(self.lock_path):
            pass
        # test: if the first lock wasn't released, the next one would wait or time out
        # the `finally` block correctly un-flocks the file
        # so an immediate acquisition succeeds without timing out.
        with file_lock(self.lock_path, timeout=2):
            pass

    def test_blocks_second_acquirer_until_first_releases(self):
        released_at = []

        def _hold_lock():
            with file_lock(self.lock_path):
                time.sleep(0.3)
            released_at.append(time.monotonic())

        holder = threading.Thread(target=_hold_lock)
        holder.start()
        time.sleep(0.05)  # let the holder acquire first

        with file_lock(self.lock_path, poll_interval=0.02):
            second_lock_at = time.monotonic()
        holder.join(timeout=5)

        self.assertTrue(released_at)
        # the second thread's acquisition timestamp MUST be greater than the background thread's release timestamp.
        self.assertGreaterEqual(second_lock_at, released_at[0])

    def test_timeout_raises_lock_timeout_error(self):
        holder_release = threading.Event()

        def _hold_lock():
            with file_lock(self.lock_path):
                holder_release.wait(timeout=5)

        holder = threading.Thread(target=_hold_lock)
        holder.start()
        time.sleep(0.05)

        # Holder - the lock open with a background thread and
        # the second caller with a shorter timeout strictly aborts and raises LockTimeoutError.
        try:
            with self.assertRaises(LockTimeoutError):
                with file_lock(self.lock_path, timeout=0.2, poll_interval=0.02):
                    pass
        finally:
            holder_release.set()
            holder.join(timeout=5)

    def test_lock_released_even_if_body_raises(self):
        """The lock must be released even when the wrapped code raises, so a failed operation doesn't affect subsequent runs."""
        class _MockException(Exception):
            pass

        with self.assertRaises(_MockException):
            with file_lock(self.lock_path):
                raise _MockException("something went wrong inside the critical section (locked section)")

        # if the lock leaked, this would hang/time out
        with file_lock(self.lock_path, timeout=2):
            pass

    def test_no_timeout_waits_indefinitely_until_released(self):
        """timeout=None (the default) must keep polling, as long as the lock eventually becomes available."""
        holder_release = threading.Event()

        def _hold_lock():
            with file_lock(self.lock_path):
                holder_release.wait(timeout=2)

        holder = threading.Thread(target=_hold_lock)
        holder.start()
        time.sleep(0.05)

        def _release_shortly():
            time.sleep(0.2)
            holder_release.set()

        threading.Thread(target=_release_shortly).start()

        # a caller with `timeout=None` will not crash, but loop until the blocking thread eventually releases.
        with file_lock(self.lock_path, poll_interval=0.02):
            pass
        holder.join(timeout=5)
