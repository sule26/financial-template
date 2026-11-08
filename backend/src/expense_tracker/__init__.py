"""Expense Tracker Web — personal, local, JSON-backed expense tracker.

Package layout (dependency direction is enforced by tests/test_architecture.py):

- ``domain``    pure business rules and models (no I/O)
- ``storage``   JSON repository (atomic writes, locking, migrations, backups)
- ``profiles``  bank profile schema/loader (how to read each bank's files)
- ``importing`` file (PDF/CSV) -> ParseResult using a profile
- ``review``    staging, rules, reconciliation, confirmation
- ``sync``      inbox folder scanning, manifest, processing queue
- ``api``       FastAPI HTTP layer
"""

__version__ = "0.1.0"
