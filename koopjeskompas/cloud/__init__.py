"""Everything that knows a cloud exists: ``aws/`` and ``azure/``, one folder each.

The rest of the package (domain, ingestion, api) knows none. What they share is
``snapshots.py``: the weekly deals, copied from cloud storage to local disk.
"""
