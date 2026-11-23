# Penfold local API contract (v0.1)

Base URL: `http://127.0.0.1:8765`. All `/api/*` endpoints require header
`X-Penfold-Token` except `/api/health`. SSE and artifact downloads also accept
`?token=<token>` because `EventSource` and `<a href>` cannot set headers.

Errors use `{"detail": "..."}` with the appropriate HTTP status.

## Shapes (JSON)

```ts
type NodeType = "input" | "agent" | "command" | "condition" | "approval" | "output";

interface Position { x: number; y: number }

interface WorkflowNode {
  id: string;
  type: NodeType;
  label?: string;
  agent?: string | null;            // required for type=agent
  description?: string;
  position: Position;               // visual only, engine ignores it
  config: Record<string, unknown>;  // type-specific (see WORKFLOW_SCHEMA)
}

interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  source_handle?: "default" | "pass" | "fail";
  target_handle?: string;
  label?: string;
  config?: { max_iterations?: number; loop?: boolean };
}

interface WorkflowDefinition {
  schema_version: 1;
  metadata: { id: string; name: string; description?: string };
  inputs: Array<{ id: string; type: string; required?: boolean; default?: unknown }>;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

interface WorkflowSummary {
  id: string; name: string; description: string;
  node_count: number; updated_at: string | null;
}

interface ValidationIssue { path: string; message: string; severity: "error" | "warning" }
interface ValidationResult { valid: boolean; issues: ValidationIssue[] }

interface AgentDefinition {
  schema_version: 1;
  id: string; name: string; description: string; role: string;
  instructions: string;
  runtime: { type: "mock" | "command"; provider?: string | null; model?: string | null;
             command?: string | null; args?: string[] };
  tools: string[];
  permissions: { mode: "read_only" | "workspace_write" | "restricted";
                 read_paths: string[]; write_paths: string[]; allowed_commands: string[] };
  inputs: Array<{ name: string; type: string; required?: boolean }>;
  outputs: { format: "json" | "text"; schema?: Record<string, unknown> | null };
  timeout: number; retries: number;
  mock?: { output?: Record<string, unknown> };
}

type RunStatus = "created" | "validating" | "running" | "waiting_approval" |
                 "paused" | "completed" | "failed" | "cancelled";
type NodeStatus = "pending" | "ready" | "running" | "waiting_approval" |
                  "succeeded" | "failed" | "skipped" | "cancelled";

interface NodeState {
  node_id: string; status: NodeStatus; iteration: number;
  started_at: string | null; finished_at: string | null;
  duration_ms: number | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
  runtime: string | null;          // e.g. "mock:product-analyst"
  simulated: boolean;              // true when MockRuntime produced the output
}

interface RunDetail {
  id: string; workflow_id: string; workflow_version: number;
  status: RunStatus; inputs: Record<string, unknown>;
  outputs: Record<string, unknown> | null;
  created_at: string; started_at: string | null; finished_at: string | null;
  error: string | null;
  approval: { node_id: string; title: string; data: unknown } | null;
  nodes: NodeState[];
}

interface RunSummary {
  id: string; workflow_id: string; status: RunStatus;
  created_at: string; finished_at: string | null; node_count: number;
}

interface RunEvent {
  id: number; run_id: string; seq: number; type: string;
  level: "info" | "success" | "warning" | "error";
  node_id: string | null; message: string;
  data: Record<string, unknown> | null; timestamp: string;
}

interface TokenInfo { token: string; url: string }
```

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/health` | – | `{status:"ok", version:string}` |
| GET | `/api/config` | – | `{project:{name,description}, defaults:{runtime}, execution:{max_concurrency,default_timeout_seconds,max_retries}}` (no secrets) |
| GET | `/api/workflows` | – | `WorkflowSummary[]` |
| GET | `/api/workflows/{id}` | – | `WorkflowDefinition` |
| PUT | `/api/workflows/{id}` | `WorkflowDefinition` | `{ok:true, id:string, issues:ValidationIssue[]}` (saves even with issues, returns 200; invalid schema itself → 422) |
| POST | `/api/workflows/validate` | `WorkflowDefinition` | `ValidationResult` |
| DELETE | `/api/workflows/{id}` | – | `{ok:true}` |
| GET | `/api/agents` | – | `AgentDefinition[]` |
| GET | `/api/agents/{id}` | – | `AgentDefinition` |
| PUT | `/api/agents/{id}` | `AgentDefinition` | `{ok:true, id:string}` |
| GET | `/api/runs?workflow_id=&limit=` | – | `RunSummary[]` |
| POST | `/api/runs` | `{workflow_id:string, inputs:Record<string,unknown>}` | `RunDetail` (201) |
| GET | `/api/runs/{id}` | – | `RunDetail` |
| GET | `/api/runs/{id}/events?after=` | – | `RunEvent[]` |
| GET | `/api/runs/{id}/stream?after=&token=` | – | `text/event-stream`, one `data: <RunEvent JSON>` per event, keeps open |
| POST | `/api/runs/{id}/cancel` | – | `{ok:true}` |
| POST | `/api/runs/{id}/resume` | – | `{ok:true}` |
| POST | `/api/runs/{id}/approve` | `{decision:"approve"|"reject"|"modify", data?:unknown, note?:string}` | `{ok:true}` |
| GET | `/api/artifacts/{run_id}/{name}` | – | file bytes |

SSE reconnects: pass `after=<last event id>` to replay missed events. Send a
heartbeat comment (`: keep-alive`) every 15 s.

## Node `config` reference

| Node type | Config keys |
|---|---|
| `input` | `{}` (workflow inputs are declared at top level) |
| `agent` | `agent` is top-level on the node; `inputs` mapping, `timeout`, `retries`, `context` (string[]) |
| `command` | `command` (string, shlex-split, no shell), `cwd` (relative path inside repo), `timeout`, `inputs` mapping |
| `condition` | `expression: {field, op, value}`, `inputs` mapping. Ops: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`, `in`, `exists`. Result branches: `pass` / `fail` |
| `approval` | `title`, `message`, `inputs` mapping |
| `output` | `inputs` mapping, `format`: `json` \| `summary` |

**Mapping values** are declarative strings, never evaluated as code:
- `$inputs.<name>` → workflow input
- `$nodes.<node_id>.output` → whole output object of a node
- `$nodes.<node_id>.output.<dotted.path>` → nested field
- `$nodes.<node_id>.status` → node status
- any other string → literal value

## Cancellation / approval semantics

- `POST cancel` sets a cancellation flag; engine stops between nodes and marks
  running node `cancelled`.
- `approval` node → run goes `waiting_approval`, `NodeState.status=waiting_approval`.
  `approve` resumes; `reject` fails the node/run; `modify` replaces output with
  supplied `data`.
- Interrupted `running` runs are marked `paused` at server start; `resume`
  restarts them from persisted checkpoints without re-running succeeded nodes.
