import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { AlertTriangle, FlaskConical } from 'lucide-react';
import { NODE_META } from '../nodeMeta';
import type { PenfoldFlowNode, PenfoldNodeData } from '../store';
import type { NodeStatus } from '../types';
import { NODE_ICONS } from './NodeLibrary';

const STATUS_LABELS: Record<NodeStatus, string> = {
  pending: 'pendiente',
  ready: 'listo',
  running: 'ejecutando',
  waiting_approval: 'aprobación',
  succeeded: 'correcto',
  failed: 'fallido',
  skipped: 'omitido',
  cancelled: 'cancelado',
};

function isIncomplete(data: PenfoldNodeData): boolean {
  const { nodeType, config, agent } = data;
  switch (nodeType) {
    case 'agent':
      return !agent;
    case 'command':
      return !config.command;
    case 'condition': {
      const expression = config.expression;
      return !expression || typeof expression !== 'object' || !('field' in expression) || !expression.field;
    }
    case 'approval':
      return !config.title;
    case 'output': {
      const inputs = config.inputs;
      return !!inputs && typeof inputs === 'object' && Object.keys(inputs).length === 0;
    }
    default:
      return false;
  }
}

function PenfoldNodeComponent({ data, selected }: NodeProps<PenfoldFlowNode>) {
  const Icon = NODE_ICONS[data.nodeType];
  const status = data.status;
  const incomplete = isIncomplete(data);
  const statusClass = status ? `status-${status}` : 'status-idle';

  return (
    <div
      className={[
        'pf-node',
        `node-${data.nodeType}`,
        selected ? 'is-selected' : '',
        status ? `has-status ${statusClass}` : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <Handle type="target" position={Position.Left} className="pf-handle" aria-label="Entrada" />

      <div className="pf-node-head">
        <span className="pf-node-icon" aria-hidden="true">
          <Icon size={16} strokeWidth={1.9} />
        </span>
        <span className="pf-node-title" title={data.label}>
          {data.label || NODE_META[data.nodeType].label}
        </span>
        {incomplete && (
          <span title="Configuración incompleta" className="warn-wrap">
            <AlertTriangle size={13} className="warn-icon" aria-label="Configuración incompleta" />
          </span>
        )}
      </div>

      <div className="pf-node-meta">
        <span className="pf-node-type">{NODE_META[data.nodeType].label}</span>
        {status && (
          <span className={`status-badge ${statusClass}`} title={`Estado: ${STATUS_LABELS[status]}`}>
            <i className="status-dot" aria-hidden="true" />
            {STATUS_LABELS[status]}
          </span>
        )}
      </div>

      {data.agent && data.nodeType === 'agent' && (
        <div className="pf-node-sub monospace" title={data.agent}>
          {data.agent}
        </div>
      )}
      {data.description && <div className="pf-node-desc">{data.description}</div>}

      {(data.simulated || data.mockRuntime) && (
        <div className="pf-node-sim" title="La salida fue producida por MockRuntime (simulada)">
          <FlaskConical size={11} aria-hidden="true" />
          SIMULADO
        </div>
      )}

      {data.nodeType === 'condition' ? (
        <>
          <div className="branch-label branch-pass" aria-hidden="true">pass</div>
          <Handle
            id="pass"
            type="source"
            position={Position.Right}
            className="pf-handle handle-pass"
            style={{ top: '38%' }}
          />
          <div className="branch-label branch-fail" aria-hidden="true">fail</div>
          <Handle
            id="fail"
            type="source"
            position={Position.Right}
            className="pf-handle handle-fail"
            style={{ top: '72%' }}
          />
        </>
      ) : (
        <Handle id="default" type="source" position={Position.Right} className="pf-handle" />
      )}
    </div>
  );
}

export const PenfoldNode = memo(PenfoldNodeComponent);
