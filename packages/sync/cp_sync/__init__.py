from cp_sync.connector_factory import UnsupportedPlatformError, build_connector
from cp_sync.products import SyncFailure, SyncResult, sync_products
from cp_sync.retry import retry_with_backoff

__all__ = [
    "SyncFailure",
    "SyncResult",
    "UnsupportedPlatformError",
    "build_connector",
    "retry_with_backoff",
    "sync_products",
]
