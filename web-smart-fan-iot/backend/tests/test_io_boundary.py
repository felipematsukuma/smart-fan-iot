from threading import Event

import pytest

from app.io_boundary import BoundedIO


def test_timeout_does_not_allow_an_unbounded_queue():
    boundary = BoundedIO(workers=1, timeout_seconds=0.02)
    release = Event()
    second_started = Event()
    try:
        with pytest.raises(TimeoutError):
            boundary.call(lambda: release.wait(2))
        with pytest.raises(TimeoutError):
            boundary.call(lambda: second_started.set())
        assert not second_started.is_set()
    finally:
        release.set()
        boundary.close()


def test_storage_exception_releases_capacity():
    boundary = BoundedIO(workers=1, timeout_seconds=1)
    try:

        def unavailable():
            raise OSError("storage unavailable")

        with pytest.raises(OSError):
            boundary.call(unavailable)
        assert boundary.call(lambda: "recovered") == "recovered"
    finally:
        boundary.close()
