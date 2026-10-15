import fcntl
import json
import os
import random
import re
import shlex
import socket
import struct
import subprocess
import sys
import time
from .paths import *
_power_cache = (None, {})


def power_policy():
    global _power_cache
    try:
        stamp = os.stat(POWER_STATE).st_mtime_ns
        if stamp != _power_cache[0]:
            with open(POWER_STATE) as stream:
                state = json.load(stream)
            _power_cache = (stamp, dict(state.get('policy', {}), mode=state.get('mode', 'complete')))
        return _power_cache[1]
    except (OSError, ValueError, TypeError):
        return {}


def is_disabled():
    return os.path.isfile(DISABLED_FLAG) or not power_policy().get('widgets', True)
