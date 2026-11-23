import { create } from 'zustand';
import {
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react';
import { NODE_META } from './nodeMeta';
import type {
  AgentDefinition,
  NodeState,
  NodeStatus,
  NodeType,
  Position,
  SourceHandle,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowInput,
  WorkflowMetadata,
  WorkflowNode,
} from './types';

export interface PenfoldNodeData extends Record<string, unknown> {
  nodeType: NodeType;
  label: string;
  description: string;
  agent: string | null;
  config: Record<string, unknown>;
  /** El agente seleccionado usa MockRuntime (informativo, no ejecuta nada aquí). */
  mockRuntime: boolean;
  status?: NodeStatus;
  simulated?: boolean;
  runtime?: string | null;
  attempts?: number;
}

export type PenfoldFlowNode = Node<PenfoldNodeData, 'penfold'>;

export interface ConnectionLike {
  source: string | null;
  target: string | null;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

interface Snapshot {
  nodes: PenfoldFlowNode[];
  edges: Edge[];
  metadata: WorkflowMetadata;
  inputs: WorkflowInput[];
}

export interface WorkflowStore {
  nodes: PenfoldFlowNode[];
  edges: Edge[];
  metadata: WorkflowMetadata;
  inputs: WorkflowInput[];
  selectedNodeId: string | null;
  dirty: boolean;
  saving: boolean;
  agents: AgentDefinition[];
  nodeStates: Record<string, NodeState>;
  past: Snapshot[];
  future: Snapshot[];
  dragging: boolean;

  addNode: (type: NodeType, position: Position) => string;
  updateNodeConfig: (id: string, patch: Record<string, unknown>) => void;
  updateNodeData: (id: string, patch: Partial<PenfoldNodeData>) => void;
  onNodesChange: (changes: NodeChange<PenfoldFlowNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<Edge>[]) => void;
  connect: (connection: ConnectionLike) => void;
  deleteSelection: () => void;
  newWorkflow: () => void;
  loadWorkflow: (definition: WorkflowDefinition) => void;
  ensureWorkflowId: () => string;
  setMetadata: (patch: Partial<WorkflowMetadata>) => void;
  setInputs: (inputs: WorkflowInput[]) => void;
  setSelectedNodeId: (id: string | null) => void;
  setAgents: (agents: AgentDefinition[]) => void;
  setNodeStates: (states: NodeState[]) => void;
  setSaving: (saving: boolean) => void;
  markSaved: () => void;
  undo: () => void;
  redo: () => void;
}

const MAX_HISTORY = 60;

export function makeId(prefix = 'n'): string {
  const uuid = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36)}`;
  return `${prefix}_${uuid}`;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function snapshot(state: WorkflowStore): Snapshot {
  return clone({
    nodes: state.nodes,
    edges: state.edges,
    metadata: state.metadata,
    inputs: state.inputs,
  });
}

function recordHistory(state: WorkflowStore): Pick<WorkflowStore, 'past' | 'future'> {
  return {
    past: [...state.past, snapshot(state)].slice(-MAX_HISTORY),
    future: [],
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function sourceTypeOf(node: PenfoldFlowNode | undefined): NodeType | undefined {
  return node?.data.nodeType;
}

/** Reglas de conexión compartidas por el canvas y el store. */
export function isValidConnection(
  connection: ConnectionLike,
  nodes: PenfoldFlowNode[],
  edges: Edge[],
): boolean {
  const { source, target } = connection;
  if (!source || !target || source === target) return false;

  const sourceNode = nodes.find((node) => node.id === source);
  const targetNode = nodes.find((node) => node.id === target);
  if (!sourceNode || !targetNode) return false;
  if (sourceTypeOf(sourceNode) === 'output') return false;
  if (sourceTypeOf(targetNode) === 'input') return false;

  const handle = connection.sourceHandle ?? 'default';
  if (sourceNode.data.nodeType === 'condition' && handle !== 'pass' && handle !== 'fail') {
    return false;
  }
  if (sourceNode.data.nodeType !== 'condition' && handle !== 'default') return false;

  const duplicate = edges.some(
    (edge) =>
      edge.source === source &&
      edge.target === target &&
      (edge.sourceHandle ?? 'default') === handle &&
      (edge.targetHandle ?? null) === (connection.targetHandle ?? null),
  );
  if (duplicate) return false;

  // Cada rama de una condición sólo puede tener una arista saliente.
  if (sourceNode.data.nodeType === 'condition') {
    return !edges.some(
      (edge) => edge.source === source && (edge.sourceHandle ?? 'default') === handle,
    );
  }
  return true;
}

function buildNode(definition: WorkflowNode, agents: AgentDefinition[]): PenfoldFlowNode {
  const type = definition.type;
  const agent = definition.agent ?? null;
  const detected = agents.find((item) => item.id === agent);
  return {
    id: definition.id,
    type: 'penfold',
    position: {
      x: Number.isFinite(definition.position?.x) ? definition.position.x : 0,
      y: Number.isFinite(definition.position?.y) ? definition.position.y : 0,
    },
    data: {
      nodeType: type,
      label: definition.label || NODE_META[type].label,
      description: definition.description ?? '',
      agent,
      mockRuntime: detected?.runtime.type === 'mock',
      config: clone(isRecord(definition.config) ? definition.config : NODE_META[type].defaultConfig()),
    },
  };
}

export function definitionToState(
  definition: WorkflowDefinition,
  agents: AgentDefinition[] = [],
): {
  nodes: PenfoldFlowNode[];
  edges: Edge[];
  metadata: WorkflowMetadata;
  inputs: WorkflowInput[];
} {
  return {
    nodes: (definition.nodes ?? []).map((node) => buildNode(node, agents)),
    edges: (definition.edges ?? []).map((edge) => ({
      id: edge.id || makeId('e'),
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.source_handle ?? 'default',
      targetHandle: edge.target_handle ?? null,
      label: edge.label,
      data: edge.config ? { config: clone(edge.config) } : undefined,
    })),
    metadata: {
      id: definition.metadata?.id ?? '',
      name: definition.metadata?.name ?? 'Sin título',
      description: definition.metadata?.description ?? '',
    },
    inputs: (definition.inputs ?? []).map((input) => ({ ...input })),
  };
}

export function workflowToDefinition(state: {
  nodes: PenfoldFlowNode[];
  edges: Edge[];
  metadata: WorkflowMetadata;
  inputs: WorkflowInput[];
}): WorkflowDefinition {
  return {
    schema_version: 1,
    metadata: {
      id: state.metadata.id,
      name: state.metadata.name,
      ...(state.metadata.description ? { description: state.metadata.description } : {}),
    },
    inputs: state.inputs.map((input) => ({ ...input })),
    nodes: state.nodes.map((node) => {
      const definition: WorkflowNode = {
        id: node.id,
        type: node.data.nodeType,
        label: node.data.label,
        position: { x: Math.round(node.position.x), y: Math.round(node.position.y) },
        config: clone(isRecord(node.data.config) ? node.data.config : {}),
      };
      if (node.data.description) definition.description = node.data.description;
      if (node.data.nodeType === 'agent') definition.agent = node.data.agent;
      return definition;
    }),
    edges: state.edges.map((edge): WorkflowEdge => {
      const result: WorkflowEdge = {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        source_handle: (edge.sourceHandle as SourceHandle | null | undefined) ?? 'default',
      };
      if (edge.targetHandle) result.target_handle = edge.targetHandle;
      if (typeof edge.label === 'string') result.label = edge.label;
      if (isRecord(edge.data) && isRecord(edge.data.config)) {
        result.config = clone(edge.data.config) as WorkflowEdge['config'];
      }
      return result;
    }),
  };
}

export function createEmptyWorkflow(): WorkflowDefinition {
  return {
    schema_version: 1,
    metadata: { id: '', name: 'Nuevo workflow', description: '' },
    inputs: [],
    nodes: [],
    edges: [],
  };
}

export const useWorkflowStore = create<WorkflowStore>((set, get) => {
  const applyHistory = (changes: () => Partial<WorkflowStore>): void => {
    const state = get();
    set({ ...recordHistory(state), dirty: true, ...changes() });
  };

  return {
    ...definitionToState(createEmptyWorkflow()),
    selectedNodeId: null,
    dirty: false,
    saving: false,
    agents: [],
    nodeStates: {},
    past: [],
    future: [],
    dragging: false,

    addNode: (type, position) => {
      const id = makeId('node');
      const data: PenfoldNodeData = {
        nodeType: type,
        label: NODE_META[type].label,
        description: '',
        agent: null,
        mockRuntime: false,
        config: NODE_META[type].defaultConfig(),
      };
      applyHistory(() => ({
        nodes: [...get().nodes, { id, type: 'penfold', position, data, selected: true }],
        selectedNodeId: id,
      }));
      return id;
    },

    updateNodeConfig: (id, patch) => {
      applyHistory(() => ({
        nodes: get().nodes.map((node) =>
          node.id === id
            ? { ...node, data: { ...node.data, config: { ...node.data.config, ...patch } } }
            : node,
        ),
      }));
    },

    updateNodeData: (id, patch) => {
      applyHistory(() => ({
        nodes: get().nodes.map((node) => {
          if (node.id !== id) return node;
          const data = { ...node.data, ...patch };
          if (patch.agent !== undefined) {
            data.mockRuntime =
              get().agents.find((agent) => agent.id === patch.agent)?.runtime.type === 'mock';
          }
          return { ...node, data };
        }),
      }));
    },

    onNodesChange: (changes) => {
      const state = get();
      const removedIds = new Set(
        changes.filter((change) => change.type === 'remove').map((change) => change.id),
      );
      const dragStarted = changes.some(
        (change) => change.type === 'position' && change.dragging === true,
      );
      const dragEnded = changes.some(
        (change) => change.type === 'position' && change.dragging === false,
      );
      const structural =
        removedIds.size > 0 || (dragStarted && !state.dragging) || changes.some((c) => c.type === 'add');

      const patch: Partial<WorkflowStore> = {
        nodes: applyNodeChanges(changes, state.nodes),
        dragging: dragStarted ? true : dragEnded ? false : state.dragging,
      };
      if (removedIds.size > 0) {
        patch.edges = state.edges.filter(
          (edge) => !removedIds.has(edge.source) && !removedIds.has(edge.target),
        );
      }
      if (removedIds.has(state.selectedNodeId ?? '')) patch.selectedNodeId = null;

      if (structural) set({ ...recordHistory(state), dirty: true, ...patch });
      else set(patch);
    },

    onEdgesChange: (changes) => {
      const state = get();
      const structural = changes.some((change) => change.type === 'remove' || change.type === 'add');
      const patch: Partial<WorkflowStore> = { edges: applyEdgeChanges(changes, state.edges) };
      if (structural) set({ ...recordHistory(state), dirty: true, ...patch });
      else set(patch);
    },

    connect: (connection) => {
      const state = get();
      if (!isValidConnection(connection, state.nodes, state.edges)) return;
      const sourceNode = state.nodes.find((node) => node.id === connection.source);
      const handle =
        sourceNode?.data.nodeType === 'condition'
          ? ((connection.sourceHandle === 'fail' ? 'fail' : 'pass') as SourceHandle)
          : ('default' as SourceHandle);
      const edge: Edge = {
        id: makeId('edge'),
        source: connection.source as string,
        target: connection.target as string,
        sourceHandle: handle,
        targetHandle: connection.targetHandle ?? null,
      };
      applyHistory(() => ({ edges: [...get().edges, edge] }));
    },

    deleteSelection: () => {
      const state = get();
      const selectedNodes = new Set(
        state.nodes.filter((node) => node.selected || node.id === state.selectedNodeId).map((n) => n.id),
      );
      const selectedEdges = new Set(
        state.edges.filter((edge) => edge.selected).map((edge) => edge.id),
      );
      if (selectedNodes.size === 0 && selectedEdges.size === 0) return;
      applyHistory(() => ({
        nodes: get().nodes.filter((node) => !selectedNodes.has(node.id)),
        edges: get().edges.filter(
          (edge) =>
            !selectedEdges.has(edge.id) && !selectedNodes.has(edge.source) && !selectedNodes.has(edge.target),
        ),
        selectedNodeId: selectedNodes.has(get().selectedNodeId ?? '') ? null : get().selectedNodeId,
      }));
    },

    newWorkflow: () => {
      const empty = definitionToState(createEmptyWorkflow());
      set({ ...empty, selectedNodeId: null, nodeStates: {}, past: [], future: [], dirty: false });
    },

    loadWorkflow: (definition) => {
      const loaded = definitionToState(definition, get().agents);
      set({
        ...loaded,
        selectedNodeId: null,
        nodeStates: {},
        past: [],
        future: [],
        dirty: false,
        saving: false,
      });
    },

    ensureWorkflowId: () => {
      const state = get();
      if (state.metadata.id) return state.metadata.id;
      const id = makeId('wf');
      set({ metadata: { ...state.metadata, id }, dirty: true });
      return id;
    },

    setMetadata: (patch) => {
      applyHistory(() => ({ metadata: { ...get().metadata, ...patch } }));
    },

    setInputs: (inputs) => {
      applyHistory(() => ({ inputs: inputs.map((input) => ({ ...input })) }));
    },

    setSelectedNodeId: (id) => set({ selectedNodeId: id }),

    setAgents: (agents) => {
      const agentIds = new Map(agents.map((agent) => [agent.id, agent]));
      set({
        agents,
        nodes: get().nodes.map((node) => {
          const agent = node.data.agent ? agentIds.get(node.data.agent) : undefined;
          const mockRuntime = agent?.runtime.type === 'mock';
          return node.data.mockRuntime === mockRuntime
            ? node
            : { ...node, data: { ...node.data, mockRuntime } };
        }),
      });
    },

    setNodeStates: (states) => {
      const byId = new Map(states.map((state) => [state.node_id, state]));
      set({
        nodeStates: Object.fromEntries(byId),
        nodes: get().nodes.map((node) => {
          const state = byId.get(node.id);
          if (!state) return node;
          return {
            ...node,
            data: {
              ...node.data,
              status: state.status,
              simulated: state.simulated,
              runtime: state.runtime,
              attempts: state.attempts,
            },
          };
        }),
      });
    },

    setSaving: (saving) => set({ saving }),

    markSaved: () => set({ dirty: false }),

    undo: () => {
      const state = get();
      const previous = state.past[state.past.length - 1];
      if (!previous) return;
      set({
        ...clone(previous),
        past: state.past.slice(0, -1),
        future: [snapshot(state), ...state.future].slice(0, MAX_HISTORY),
        dirty: true,
        dragging: false,
      });
    },

    redo: () => {
      const state = get();
      const next = state.future[0];
      if (!next) return;
      set({
        ...clone(next),
        past: [...state.past, snapshot(state)].slice(-MAX_HISTORY),
        future: state.future.slice(1),
        dirty: true,
        dragging: false,
      });
    },
  };
});

export function selectDefinition(state: WorkflowStore): WorkflowDefinition {
  return workflowToDefinition(state);
}

/** Helper para tests y para el botón "Demo": construye un workflow de ejemplo. */
export function demoWorkflow(): WorkflowDefinition {
  const inputId = makeId('node');
  const agentId = makeId('node');
  const outputId = makeId('node');
  return {
    schema_version: 1,
    metadata: { id: '', name: 'Demo — análisis', description: 'Input → Agent → Output' },
    inputs: [{ id: 'tema', type: 'string', required: true, default: 'rendimiento del equipo' }],
    nodes: [
      {
        id: inputId,
        type: 'input',
        label: 'Entrada',
        position: { x: 60, y: 160 },
        config: {},
      },
      {
        id: agentId,
        type: 'agent',
        label: 'Analista',
        agent: null,
        position: { x: 360, y: 160 },
        config: { inputs: { tema: '$inputs.tema' }, timeout: 30, retries: 0, context: [] },
      },
      {
        id: outputId,
        type: 'output',
        label: 'Resultado',
        position: { x: 660, y: 160 },
        config: { inputs: { resultado: `$nodes.${agentId}.output` }, format: 'json' },
      },
    ],
    edges: [
      { id: makeId('edge'), source: inputId, target: agentId, source_handle: 'default' },
      { id: makeId('edge'), source: agentId, target: outputId, source_handle: 'default' },
    ],
  };
}

export type { Connection };
