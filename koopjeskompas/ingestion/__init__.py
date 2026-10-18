"""Ingestion: pulls deals from external sources into validated domain models.

Runs as a separate CLI step, never inside a request. External payload shapes stay in
this package; only domain ``Deal`` models leave it.
"""
