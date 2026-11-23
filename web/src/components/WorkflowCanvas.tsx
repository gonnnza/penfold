import { useCallback, useEffect, useMemo, type DragEvent } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useReactFlow,
  type Connection,
  type Edge,
  type IsValidConnection,
  type NodeTypes,
} from '@xyflow/react';
import { isNodeType } from '../nodeMeta';
import { isValidConnection, useWorkflowStore } from '../store';
import { NODE_DRAG_MIME } from './NodeLibrary';
import { PenfoldNode } from './PenfoldNode';

const nodeTypes: NodeTypes = { penfold: PenfoldNode };

const MINIMAP_COLORS: Record<string, string> = {
  input: '#3b82f6',
  agent: '#a78bfa',
  command: '#22d3ee',
  condition: '#f59e0b',
  approval: '#f472b6',
  output: '#34d399',
};

export function WorkflowCanvas() {
  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const nodeStates = useWorkflowStore((state) => state.nodeStates);
  const workflowId = useWorkflowStore((state) => state.metadata.id);
  const onNodesChange = useWorkflowStore((state) => state.onNodesChange);
  const onEdgesChange = useWorkflowStore((state) => state.onEdgesChange);
  const connect = useWorkflowStore((state) => state.connect);
  const addNode = useWorkflowStore((state) => state.addNode);
  const setSelectedNodeId = useWorkflowStore((state) => state.setSelectedNodeId);
  const { fitView, screenToFlowPosition } = useReactFlow();

  useEffect(() => {
    const timer = setTimeout(() => {
      void fitView({ padding: 0.25, duration: 250 });
    }, 30);
    return () => clearTimeout(timer);
  }, [fitView, workflowId]);

  const flowEdges = useMemo(
    () =>
      edges.map((edge) => {
        const sourceState = nodeStates[edge.source];
        const active = sourceState?.status === 'running' || sourceState?.status === 'succeeded';
        const color =
          sourceState?.status === 'running'
            ? 'var(--accent)'
            : sourceState?.status === 'succeeded'
              ? 'var(--ok)'
              : 'var(--edge)';
        return {
          ...edge,
          animated: active,
          style: { stroke: color, strokeWidth: active ? 2.2 : 1.4 },
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
        };
      }),
    [edges, nodeStates],
  );

  const checkConnection = useCallback<IsValidConnection>(
    (connection: Connection | Edge) => isValidConnection(connection, nodes, edges),
    [nodes, edges],
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const type = event.dataTransfer.getData(NODE_DRAG_MIME);
      if (!isNodeType(type)) return;
      const point = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      addNode(type, { x: Math.round(point.x - 90), y: Math.round(point.y - 25) });
    },
    [addNode, screenToFlowPosition],
  );

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  return (
    <div className="canvas-wrap" onDrop={onDrop} onDragOver={onDragOver}>
      <ReactFlow
        nodes={nodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={connect}
        isValidConnection={checkConnection}
        onNodeClick={(_, node) => setSelectedNodeId(node.id)}
        onPaneClick={() => setSelectedNodeId(null)}
        deleteKeyCode={null}
        multiSelectionKeyCode={['Shift', 'Control']}
        minZoom={0.25}
        maxZoom={2}
        fitView
        proOptions={{ hideAttribution: false }}
        aria-label="Editor de workflow"
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="var(--grid)" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(node) => MINIMAP_COLORS[String(node.data?.nodeType ?? '')] ?? '#64748b'}
          maskColor="rgba(5, 9, 15, 0.78)"
        />
      </ReactFlow>
      {nodes.length === 0 && (
        <div className="canvas-empty" aria-live="polite">
          <strong>Canvas vacío</strong>
          <span>Arrastra un nodo desde la librería o usa el botón Demo.</span>
        </div>
      )}
    </div>
  );
}
