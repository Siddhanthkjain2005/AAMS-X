"""Version identifiers recorded with every experiment.

``SCHEDULER_VERSION`` is bumped whenever a policy's behaviour changes, so a stored
result can never be silently compared against a different algorithm wearing the
same name.
"""

from __future__ import annotations

__version__ = "1.0.0"
CODE_VERSION = __version__
SCHEDULER_VERSION = "mag-nts/1.0"
CONTRACT_VERSION = "aamsx-contracts/2"
