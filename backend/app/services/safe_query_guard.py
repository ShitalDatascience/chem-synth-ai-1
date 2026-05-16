"""Pre-router input sanitisation.

Runs as the **very first** step in the chat pipeline:

    raw_user_input  →  safe_query_guard.safe_guard()
                       └─► IntentRouter
                             └─► EntityResolver
                                   └─► ToolSelector
                                         └─► Execution
                                               └─► LLM (final summariser only)

Blocks empty input and obvious prompt-injection patterns BEFORE any
classification, RDKit, ChEMBL, Milvus, DeepChem or LLM tool call happens.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


# Phrases commonly used in prompt-injection / jailbreak attempts.
_BLOCKED_PATTERNS: List[str] = [
    "ignore previous",
    "ignore the previous",
    "ignore all previous",
    "ignore all instructions",
    "disregard previous",
    "system prompt",
    "system: you are",
    "policy override",
    "override policy",
    "jailbreak",
    "developer mode",
    "you are now dan",
    "act as if",
    "pretend you are",
    "forget everything",
    "reveal your instructions",
    "print your prompt",
]

# Hard size cap — protects downstream tools from runaway payloads.
MAX_QUERY_LENGTH = 4_000


@dataclass(frozen=True)
class GuardResult:
    block: bool
    reason: Optional[str] = None
    sanitized_query: Optional[str] = None


def safe_guard(user_input: Optional[str]) -> GuardResult:
    """Pre-process and sanitise ``user_input`` before routing.

    Returns a :class:`GuardResult`:
      * ``block=True``  → caller must short-circuit and return a
                          ``blocked_safe_mode`` envelope to the user.
      * ``block=False`` → caller may proceed using ``sanitized_query``.
    """
    if user_input is None:
        return GuardResult(block=True, reason="empty_query")

    # Strip and collapse runs of whitespace; protect against zero-width nasties.
    cleaned = " ".join(user_input.split()).strip()
    if not cleaned:
        return GuardResult(block=True, reason="empty_query")

    if len(cleaned) > MAX_QUERY_LENGTH:
        logger.info("[GUARD] truncating oversized input (%d chars)", len(cleaned))
        cleaned = cleaned[:MAX_QUERY_LENGTH]

    lowered = cleaned.lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in lowered:
            logger.warning("[GUARD] blocked prompt-injection pattern: %r", pattern)
            return GuardResult(block=True, reason="prompt_injection")

    return GuardResult(block=False, sanitized_query=cleaned)
