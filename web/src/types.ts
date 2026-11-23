/** Tipos derivados de docs/development/API_CONTRACT.md (v0.1). */

export type NodeType = 'input' | 'agent' | 'command' | 'condition' | 'approval' | 'output';

export interface Position {
  x: number;
  y: number;
}

export interface WorkflowNode {
  id: string;
  type: NodeType;
  label?: string;
  agent?: string | null;
  description?: string;
  position: Position;
  config: Record<string, unknown>;
}

export type SourceHandle = 'default' | 'pass' | 'fail';

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  source_handle?: SourceHandle;
  target_handle?: string;
  label?: string;
  config?: { max_iterations?: number; loop?: boolean };
}

export interface WorkflowInput {
  id: string;
  type: string;
  required?: boolean;
  default?: unknown;
}

export interface WorkflowMetadata {
  id: string;
  name: string;
  description?: string;
}

export interface WorkflowDefinition {
  schema_version: 1;
  metadata: WorkflowMetadata;
  inputs: WorkflowInput[];
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  node_count: number;
  updated_at: string | null;
}

export interface ValidationIssue {
  path: string;
  message: string;
  severity: 'error' | 'warning';
}

export interface ValidationResult {
  valid: boolean;
  issues: ValidationIssue[];
}

export interface AgentDefinition {
  schema_version: 1;
  id: string;
  name: string;
  description: string;
  role: string;
  instructions: string;
  runtime: {
    type: 'mock' | 'command';
    provider?: string | null;
    model?: string | null;
    command?: string | null;
    args?: string[];
  };
  tools: string[];
  permissions: {
    mode: 'read_only' | 'workspace_write' | 'restricted';
    read_paths: string[];
    write_paths: string[];
    allowed_commands: string[];
  };
  inputs: Array<{ name: string; type: string; required?: boolean }>;
  outputs: { format: 'json' | 'text'; schema?: Record<string, unknown> | null };
  timeout: number;
  retries: number;
  mock?: { output?: Record<string, unknown> };
}

export type RunStatus =
  | 'created'
  | 'validating'
  | 'running'
  | 'waiting_approval'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type NodeStatus =
  | 'pending'
  | 'ready'
  | 'running'
  | 'waiting_approval'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'cancelled';

export interface NodeState {
  node_id: string;
  status: NodeStatus;
  iteration: number;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
  runtime: string | null;
  simulated: boolean;
}

export interface RunDetail {
  id: string;
  workflow_id: string;
  workflow_version: number;
  status: RunStatus;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  approval: { node_id: string; title: string; data: unknown } | null;
  nodes: NodeState[];
}

export interface RunSummary {
  id: string;
  workflow_id: string;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  node_count: number;
}

export type EventLevel = 'info' | 'success' | 'warning' | 'error';

export interface RunEvent {
  id: number;
  run_id: string;
  seq: number;
  type: string;
  level: EventLevel;
  node_id: string | null;
  message: string;
  data: Record<string, unknown> | null;
  timestamp: string;
}

export interface TokenInfo {
  token: string;
  url: string;
}

export interface AppConfig {
  project: { name: string; description: string };
  defaults: { runtime: string };
  execution: {
    max_concurrency: number;
    default_timeout_seconds: number;
    max_retries: number;
  };
}

export interface HealthStatus {
  status: string;
  version: string;
}

export type ApprovalDecision = 'approve' | 'reject' | 'modify';

/** Mapa clave -> expresión declarativa (`$inputs.x`, `$nodes.<id>.output...` o literal). */
export type InputMapping = Record<string, unknown>;
