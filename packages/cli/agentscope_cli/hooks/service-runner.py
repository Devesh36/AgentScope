"""Stop owned children when the watch/run parent disappears unexpectedly."""

import os
import signal
import subprocess
import sys
import time

owner = int(sys.argv[1])
stopping = False


def request_stop(*_):
    global stopping
    stopping = True


# The whole owned group receives termination. Keep the supervisor alive until
# its child has drained, so the CLI can wait for real service shutdown.
signal.signal(signal.SIGTERM, request_stop)
child = subprocess.Popen(sys.argv[2:])
while child.poll() is None:
    if os.getppid() != owner and not stopping:
        # The runner and its children have a dedicated session/process group.
        os.killpg(os.getpgrp(), signal.SIGTERM)
    time.sleep(0.25)
sys.exit(child.returncode)
