"""Dibujo del grafo de un workflow en la terminal (estilo draw.io en ASCII).

La capa de presentación calcula la disposición por niveles a partir de las
aristas; no usa ``position`` (que es solo decorativa) ni depende del motor.
"""

from __future__ import annotations

from collections import defaultdict, deque

from rich import get_console
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from penfold.models.workflow import WorkflowDefinition, WorkflowEdge

BOX_HEIGHT = 5
ROW_GAP = 2
COL_GAP = 8

TYPE_LABEL = {
    "input": "INPUT",
    "agent": "AGENTE",
    "command": "COMANDO",
    "condition": "CONDICIÓN",
    "approval": "APROBACIÓN",
    "output": "OUTPUT",
}


def _levels(workflow: WorkflowDefinition) -> dict[str, int]:
    """Nivel = camino más largo desde una raíz, ignorando aristas de retorno.

    Primero se detectan los back edges con un DFS (color blanco/gris/negro) y
    después se calculan los niveles con un orden topológico (Kahn) sobre el
    grafo acíclico resultante.
    """
    ids = {node.id for node in workflow.nodes}
    edges = [e for e in workflow.edges if e.source in ids and e.target in ids]
    adjacency: dict[str, list[WorkflowEdge]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source].append(edge)

    color: dict[str, int] = {}
    # Las aristas marcadas como bucle son la señal semántica del retorno; el
    # DFS solo detecta ciclos adicionales que no estén marcados.
    back: set[str] = {edge.id for edge in edges if edge.config.loop}

    def detect(node_id: str) -> None:
        color[node_id] = 1
        for edge in adjacency[node_id]:
            if edge.id in back:
                continue
            state = color.get(edge.target, 0)
            if state == 1:
                back.add(edge.id)
            elif state == 0:
                detect(edge.target)
        color[node_id] = 2

    for node_id in ids:
        if color.get(node_id, 0) == 0:
            detect(node_id)

    dag: dict[str, list[WorkflowEdge]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in ids}
    for edge in edges:
        if edge.id in back:
            continue
        dag[edge.source].append(edge)
        indegree[edge.target] += 1

    level = {node_id: 0 for node_id in ids}
    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    while queue:
        source = queue.popleft()
        for edge in dag[source]:
            target = edge.target
            level[target] = max(level[target], level[source] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    # Nodos que solo tenían predecesores dentro de un ciclo: los colocamos
    # después de todos los anteriores.
    remaining = [node_id for node_id, degree in indegree.items() if degree > 0]
    if remaining:
        floor = max(level.values(), default=0) + 1
        for node_id in remaining:
            level[node_id] = floor
    return level


def _place(
    workflow: WorkflowDefinition,
) -> tuple[
    dict[str, tuple[int, int]],
    dict[str, int],
    list[WorkflowEdge],
    list[WorkflowEdge],
    int,
    int,
    int,
    int,
]:
    """Calcula posición (fila, columna) de cada nodo y clasifica las aristas."""
    level = _levels(workflow)
    grouped: dict[int, list[str]] = defaultdict(list)
    for node in workflow.nodes:
        grouped[level[node.id]].append(node.id)

    max_label = max((len(node.label or node.id) for node in workflow.nodes), default=8)
    width = min(30, max(8, max_label + 8))
    gap = COL_GAP
    level_count = len(grouped)
    available = get_console().width - 6  # bordes del Panel y padding
    if level_count > 1 and level_count * width + (level_count - 1) * gap > available:
        width = max(8, (available - (level_count - 1) * gap) // level_count)
        if level_count * width + (level_count - 1) * gap > available:
            gap = max(1, (available - level_count * width) // (level_count - 1))

    positions: dict[str, tuple[int, int]] = {}
    row = 0
    for col, lvl in enumerate(sorted(grouped)):
        for index, node_id in enumerate(grouped[lvl]):
            positions[node_id] = (row + index * (BOX_HEIGHT + ROW_GAP), col * (width + gap))
        row += len(grouped[lvl]) * (BOX_HEIGHT + ROW_GAP)

    back_edges: list[WorkflowEdge] = []
    forward: list[WorkflowEdge] = []
    for edge in workflow.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        if level[edge.target] <= level[edge.source]:
            back_edges.append(edge)
        else:
            forward.append(edge)

    rows = max((r for r, _ in positions.values()), default=0) + BOX_HEIGHT
    cols = (len(grouped) - 1) * (width + gap) + width if grouped else width
    return positions, level, forward, back_edges, rows, cols, width, gap


def _set(canvas: list[list[str]], row: int, col: int, char: str) -> None:
    if 0 <= row < len(canvas) and 0 <= col < len(canvas[row]):
        current = canvas[row][col]
        if current == " " or char in "┌┐└┘│─▶":
            canvas[row][col] = char


def _write(canvas: list[list[str]], row: int, col: int, text: str) -> None:
    for offset, char in enumerate(text):
        _set(canvas, row, col + offset, char)


def build_diagram(workflow: WorkflowDefinition) -> RenderableType:
    """Devuelve un renderizable de Rich con el grafo del workflow."""
    positions, level, forward, back_edges, rows, cols, width, gap = _place(workflow)
    canvas = [[" "] * cols for _ in range(rows)]
    labels: dict[str, str] = {}
    for node in workflow.nodes:
        text = node.label or node.id
        if len(text) > 2 * (width - 3) and len(node.id) < len(text):
            text = node.id
        labels[node.id] = text
    kinds = {node.id: TYPE_LABEL.get(node.type, node.type.upper()) for node in workflow.nodes}

    for node_id, (top, left) in positions.items():
        inner = width - 2
        kind = f" {kinds[node_id]}"[:inner].ljust(inner)
        step = inner - 1
        chunks = [labels[node_id][i : i + step] for i in range(0, len(labels[node_id]), step)][:2]
        if len(chunks) == 2 and len(labels[node_id]) > 2 * (inner - 1):
            chunks[1] = chunks[1][: inner - 4] + "..."
        label_lines = [f" {chunk}".ljust(inner) for chunk in chunks] or [" ".ljust(inner)]
        while len(label_lines) < 2:
            label_lines.append(" ".ljust(inner))

        canvas[top][left] = "┌"
        canvas[top][left + width - 1] = "┐"
        for row in (top + 1, top + 2, top + 3):
            canvas[row][left] = "│"
            canvas[row][left + width - 1] = "│"
        canvas[top + 4][left] = "└"
        canvas[top + 4][left + width - 1] = "┘"
        for offset, char in enumerate(kind):
            canvas[top + 1][left + 1 + offset] = char
        for line_index, line in enumerate(label_lines):
            for offset, char in enumerate(line):
                canvas[top + 2 + line_index][left + 1 + offset] = char
        for offset in range(inner):
            canvas[top][left + 1 + offset] = "─"
            canvas[top + 4][left + 1 + offset] = "─"

    for edge in forward:
        sy, sx = positions[edge.source]
        ty, tx = positions[edge.target]
        y1, x1 = sy + 1, sx + width
        y2, x2 = ty + 1, tx - 1
        if y1 == y2:
            for x in range(x1, x2 + 1):
                _set(canvas, y1, x, "─")
            _set(canvas, y2, x2, "▶")
        else:
            mid = x1 + max(1, gap // 2)
            for x in range(x1, mid + 1):
                _set(canvas, y1, x, "─")
            start_corner = "┐" if y1 < y2 else "┘"
            end_corner = "└" if y1 < y2 else "┌"
            _set(canvas, y1, mid, start_corner)
            lo, hi = sorted((y1, y2))
            for y in range(lo + 1, hi):
                _set(canvas, y, mid, "│")
            _set(canvas, y2, mid, end_corner)
            for x in range(mid, x2 + 1):
                _set(canvas, y2, x, "─")
            _set(canvas, y2, x2, "▶")

        label = edge.label or (edge.source_handle if edge.source_handle != "default" else "")
        if label and y1 > 0:
            _write(canvas, y1 - 1, x1 + 1, f" {label} ")

    lines = ["".join(row).rstrip() for row in canvas]
    text = Text("\n".join(lines))
    for token, style in (
        ("INPUT", "bold cyan"),
        ("AGENTE", "bold magenta"),
        ("COMANDO", "bold yellow"),
        ("CONDICIÓN", "bold red"),
        ("APROBACIÓN", "bold bright_magenta"),
        ("OUTPUT", "bold green"),
    ):
        text.highlight_regex(token, style)

    parts: list[RenderableType] = [
        Panel(text, title=f"Workflow: {workflow.metadata.name}", border_style="cyan")
    ]
    if back_edges:
        detail = "\n".join(
            f"  {labels.get(e.source, e.source)} -[{e.label or e.source_handle}]-> "
            f"{labels.get(e.target, e.target)}"
            + (f"  (max {e.config.max_iterations})" if e.config.max_iterations else "")
            for e in back_edges
        )
        parts.append(Panel(Text(detail), title="Bucles / retornos", border_style="yellow"))
    return Group(*parts)
