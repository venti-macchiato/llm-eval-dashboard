"""Serializes job claims for the single model-server slot.

Eval, prompt, and speed runs each check that the others are idle and then
publish their own running state. Those guard-and-claim pairs must be atomic:
two concurrent requests could otherwise both observe "idle" and start, driving
the server with two runs at once. All three acquire this lock around their
check plus claim.
"""

from __future__ import annotations

import threading

LOCK = threading.Lock()
