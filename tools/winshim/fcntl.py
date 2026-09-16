"""Windows stand-in for the POSIX fcntl module.

homeassistant/runner.py imports fcntl at module scope and calls flock only
inside its single-instance lock, which the test harness never takes. The stub
exists so the import succeeds; a call raises rather than pretending to lock.
"""

LOCK_EX = 2
LOCK_NB = 4
LOCK_SH = 1
LOCK_UN = 8


def flock(fd, operation):  # noqa: ANN001, ANN201
    raise OSError("flock is not available on Windows")


def lockf(fd, operation, length=0, start=0, whence=0):  # noqa: ANN001, ANN201
    raise OSError("lockf is not available on Windows")


def fcntl(fd, cmd, arg=0):  # noqa: ANN001, ANN201
    raise OSError("fcntl is not available on Windows")


def ioctl(fd, request, arg=0, mutate_flag=True):  # noqa: ANN001, ANN201
    raise OSError("ioctl is not available on Windows")
