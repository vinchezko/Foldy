"""Tiny stdlib-only helper to talk to the running Foldy app through its named pipe."""
import json, os, time

from .constants import PIPE_PATH


def send_to_hub(msg, retries=1):
    """Deliver a JSON message to the running app. True if an app received it, False if none is running."""
    data = (json.dumps(msg) + "\n").encode()
    for _ in range(retries):
        try:
            fd = os.open(PIPE_PATH, os.O_WRONLY | getattr(os, "O_BINARY", 0))
            os.write(fd, data)
            os.close(fd)
            return True
        except FileNotFoundError:
            return False                                      # no app running
        except OSError:
            time.sleep(0.03)                                  # pipe busy, retry
    return False
