"""CAPA VIEW — endpoints HTTP (FastAPI), SSE y middleware de token.

Solo transporte: delega en ``penfold.services`` y serializa ``penfold.models``.
"""

from penfold.views.app import create_app

__all__ = ["create_app"]
