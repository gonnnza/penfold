"""CAPA MODEL — solo declaración de clases (Pydantic / enums / alias de tipos).

Sin lógica de negocio, sin acceso a disco, sin FastAPI. Si necesitas comportamiento,
va en ``penfold.services``.
"""

from penfold.models.agent import (
    AgentDefinition,
    AgentInput,
    AgentOutputs,
    MockBehavior,
    Permissions,
    RuntimeSpec,
)
from penfold.models.approval import ApprovalDecision
from penfold.models.config import (
    DefaultsConfig,
    ExecutionConfig,
    ProjectConfig,
    SecurityConfig,
    ServerConfig,
)
from penfold.models.execution import (
    ApprovalInfo,
    ApprovalRequest,
    NodeState,
    NodeStatus,
    RunDetail,
    RunEvent,
    RunStatus,
    RunSummary,
    StartRunRequest,
)
from penfold.models.git import RepoInfo
from penfold.models.runtime import RuntimeContext, RuntimeResult
from penfold.models.validation import ValidationIssue
from penfold.models.workflow import (
    EdgeConfig,
    Handle,
    NodeType,
    Position,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowNode,
)

__all__ = [
    "AgentDefinition",
    "AgentInput",
    "AgentOutputs",
    "ApprovalDecision",
    "ApprovalInfo",
    "ApprovalRequest",
    "DefaultsConfig",
    "EdgeConfig",
    "ExecutionConfig",
    "Handle",
    "MockBehavior",
    "NodeState",
    "NodeStatus",
    "NodeType",
    "Permissions",
    "Position",
    "ProjectConfig",
    "RuntimeContext",
    "RuntimeResult",
    "RuntimeSpec",
    "RunDetail",
    "RunEvent",
    "RunStatus",
    "RunSummary",
    "RepoInfo",
    "SecurityConfig",
    "ServerConfig",
    "StartRunRequest",
    "ValidationIssue",
    "WorkflowDefinition",
    "WorkflowEdge",
    "WorkflowInput",
    "WorkflowMetadata",
    "WorkflowNode",
]
