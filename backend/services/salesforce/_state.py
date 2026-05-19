"""
Sync state and result tracking for Salesforce sync.

Hosts data structures that describe the outcome and progress of a
sync operation. Future home for sync checkpoint / state-machine logic.
"""
from typing import Any, Dict, List


class SyncResult:
    """Result of a sync operation"""
    def __init__(self):
        self.success = False
        self.records_processed = 0
        self.records_succeeded = 0
        self.records_failed = 0
        self.errors: List[Dict[str, str]] = []
        self.duration_ms = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'records_processed': self.records_processed,
            'records_succeeded': self.records_succeeded,
            'records_failed': self.records_failed,
            'errors': self.errors,
            'duration_ms': self.duration_ms
        }
