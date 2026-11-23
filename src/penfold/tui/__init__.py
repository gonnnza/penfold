"""Adaptador de terminal (TUI) del dashboard de Penfold.

Como ``views/``, esta capa solo presenta: delega toda la lógica en
``penfold.services`` y muestra los modelos de ``penfold.models``.
"""

from penfold.tui.dashboard import run_dashboard

__all__ = ["run_dashboard"]
