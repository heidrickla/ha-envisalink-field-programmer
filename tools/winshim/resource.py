"""Windows stand-in for the POSIX resource module.

homeassistant/util/resource.py imports it at module scope and only calls
getrlimit/setrlimit from set_open_file_descriptor_limit, which the test
harness never calls. Windows has no per-process descriptor rlimit, so the
stub reports the C runtime's fixed 8192 and refuses to change it.
"""

RLIMIT_NOFILE = 7
RLIM_INFINITY = -1

_SOFT = 8192
_HARD = 8192


def getrlimit(resource_id):  # noqa: ANN001, ANN201
    return (_SOFT, _HARD)


def setrlimit(resource_id, limits):  # noqa: ANN001, ANN201
    raise ValueError("setrlimit is not available on Windows")
