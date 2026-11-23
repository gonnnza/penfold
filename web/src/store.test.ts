import { beforeEach, describe, expect, it } from 'vitest';
import {
  createEmptyWorkflow,
  definitionToState,
  demoWorkflow,
  useWorkflowStore,
  workflowToDefinition,
  isValidConnection,
} from './store';
import type { WorkflowDefinition } from './types';

function reset(): void {
  useWorkflowStore.setState({
    ...definitionToState(createEmptyWorkflow()),
    selectedNodeId: null,
    dirty: false,
    saving: false,
    nodeStates: {},
    past: [],
    future: [],
    dragging: false,
  });
}

describe('workflow store', () => {
  beforeEach(reset);

  it('añade nodos con IDs estables, configuración por tipo y selección', () => {
    const id = useWorkflowStore.getState().addNode('agent', { x: 10, y: 20 });
    const state = useWorkflowStore.getState();

    expect(id).toMatch(/^node_/);
    expect(state.nodes).toHaveLength(1);
    expect(state.nodes[0].id).toBe(id);
    expect(state.nodes[0].data.nodeType).toBe('agent');
    expect(state.nodes[0].data.config).toMatchObject({ timeout: 30, retries: 0 });
    expect(state.nodes[0].position).toEqual({ x: 10, y: 20 });
    expect(state.selectedNodeId).toBe(id);
    expect(state.dirty).toBe(true);
  });

  it('conecta nodos aplicando las reglas del contrato', () => {
    const input = useWorkflowStore.getState().addNode('input', { x: 0, y: 0 });
    const agent = useWorkflowStore.getState().addNode('agent', { x: 200, y: 0 });

    useWorkflowStore.getState().connect({ source: input, target: input, sourceHandle: 'default' });
    expect(useWorkflowStore.getState().edges).toHaveLength(0);

    useWorkflowStore.getState().connect({ source: input, target: agent, sourceHandle: 'default' });
    expect(useWorkflowStore.getState().edges).toHaveLength(1);
    expect(useWorkflowStore.getState().edges[0]).toMatchObject({
      source: input,
      target: agent,
      sourceHandle: 'default',
    });

    // Duplicado: misma arista.
    useWorkflowStore.getState().connect({ source: input, target: agent, sourceHandle: 'default' });
    expect(useWorkflowStore.getState().edges).toHaveLength(1);
  });

  it('una condición sólo permite una salida por rama pass/fail', () => {
    const condition = useWorkflowStore.getState().addNode('condition', { x: 0, y: 0 });
    const a = useWorkflowStore.getState().addNode('output', { x: 200, y: 0 });
    const b = useWorkflowStore.getState().addNode('output', { x: 200, y: 100 });

    useWorkflowStore.getState().connect({ source: condition, target: a, sourceHandle: 'pass' });
    useWorkflowStore.getState().connect({ source: condition, target: b, sourceHandle: 'pass' });
    expect(useWorkflowStore.getState().edges).toHaveLength(1);

    useWorkflowStore.getState().connect({ source: condition, target: b, sourceHandle: 'fail' });
    expect(useWorkflowStore.getState().edges).toHaveLength(2);
    expect(useWorkflowStore.getState().edges.map((edge) => edge.sourceHandle)).toEqual([
      'pass',
      'fail',
    ]);

    const state = useWorkflowStore.getState();
    expect(isValidConnection({ source: condition, target: a, sourceHandle: 'default' }, state.nodes, state.edges)).toBe(false);
  });

  it('deshace y rehace inserciones y cambios de configuración', () => {
    const id = useWorkflowStore.getState().addNode('command', { x: 0, y: 0 });
    useWorkflowStore.getState().updateNodeConfig(id, { command: 'pytest -q' });
    expect((useWorkflowStore.getState().nodes[0].data.config as { command: unknown }).command).toBe('pytest -q');

    useWorkflowStore.getState().undo();
    expect(useWorkflowStore.getState().nodes[0].data.config.command).toBe('');

    useWorkflowStore.getState().undo();
    expect(useWorkflowStore.getState().nodes).toHaveLength(0);

    useWorkflowStore.getState().redo();
    expect(useWorkflowStore.getState().nodes).toHaveLength(1);
    useWorkflowStore.getState().redo();
    expect((useWorkflowStore.getState().nodes[0].data.config as { command: unknown }).command).toBe('pytest -q');
  });

  it('serializa y carga un workflow respetando el contrato', () => {
    useWorkflowStore.getState().loadWorkflow(demoWorkflow());
    const definition = workflowToDefinition(useWorkflowStore.getState());

    expect(definition.schema_version).toBe(1);
    expect(definition.nodes).toHaveLength(3);
    expect(definition.edges).toHaveLength(2);
    expect(definition.nodes[1]).toMatchObject({ type: 'agent' });
    expect(definition.nodes[1].agent).toBeNull();
    expect(definition.edges[0].source_handle).toBe('default');
    expect(definition.inputs[0]).toMatchObject({ id: 'tema', required: true });

    const id = useWorkflowStore.getState().ensureWorkflowId();
    expect(id).toMatch(/^wf_/);
    const roundTrip: WorkflowDefinition = JSON.parse(JSON.stringify(workflowToDefinition(useWorkflowStore.getState()))) as WorkflowDefinition;
    useWorkflowStore.getState().newWorkflow();
    expect(useWorkflowStore.getState().nodes).toHaveLength(0);
    useWorkflowStore.getState().loadWorkflow(roundTrip);
    expect(useWorkflowStore.getState().nodes).toHaveLength(3);
    expect(useWorkflowStore.getState().metadata.id).toBe(id);
    expect(useWorkflowStore.getState().dirty).toBe(false);
  });

  it('borra la selección y marca como guardado', () => {
    useWorkflowStore.getState().addNode('input', { x: 0, y: 0 });
    useWorkflowStore.getState().deleteSelection();
    expect(useWorkflowStore.getState().nodes).toHaveLength(0);
    useWorkflowStore.getState().markSaved();
    expect(useWorkflowStore.getState().dirty).toBe(false);
  });
});
