# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""CoComputer - AI agent with full Linux desktop control."""

# Apply global monkey patch to google-cloud-firestore to fix AttributeError:
# '_UnaryStreamMultiCallable' object has no attribute '_retry' on streaming queries.
try:
    from google.cloud.firestore_v1.query import Query
    from google.api_core import gapic_v1
    from google.api_core.retry import Retry

    def _patched_retry_query_after_exception(self, exc, retry, transaction):
        """Helper method for :meth:`stream` patched to handle gRPC stream callables without `_retry`."""
        if transaction is None:  # no snapshot-based retry inside transaction
            if retry is gapic_v1.method.DEFAULT:
                try:
                    transport = self._client._firestore_api._transport
                    gapic_callable = transport.run_query
                    retry = getattr(gapic_callable, "_retry", Retry())
                except Exception:
                    retry = Retry()
            try:
                return retry._predicate(exc)
            except Exception:
                return False
        return False

    Query._retry_query_after_exception = _patched_retry_query_after_exception
except ImportError:
    pass
