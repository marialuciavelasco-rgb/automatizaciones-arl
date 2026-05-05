"""
handler.py — Entry point de AWS Lambda.
La lógica vive en run_cloud.py; este archivo solo reexporta el handler.
"""
from run_cloud import lambda_handler  # noqa: F401
