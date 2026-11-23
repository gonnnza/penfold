import { useState } from 'react';
import {
  Activity,
  Ban,
  ChevronDown,
  ChevronUp,
  CircleCheck,
  CircleX,
 Eye,
  PauseCircle,
  PlayCircle,
  RotateCw,
  ScrollText,
} from 'lucide-react';
import { useWorkflowStore } from '../store';
import type { ApprovalDecision, RunDetail, RunEvent, RunStatus, RunSummary } from '../types';

interface RunPanelProps {
  runs: RunSummary[];
  run: RunDetail | null;
  events: RunEvent[];
  streamStatus: 'idle' | 'connected' | 'reconnecting';
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onSelectRun: (id: string) => void;
  onRefresh: () => void;
  onCancel: () => void;
  onResume: () => void;
  onApprove: (decision: ApprovalDecision, data?: unknown, note?: string) => void;
}

const ACTIVE_STATUSES: RunStatus[] = ['created', 'validating', 'running', 'waiting_approval', 'paused'];
const TERMINAL_STATUSES: RunStatus[] = ['completed', 'failed', 'cancelled'];

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '--:--:--';
  const pad = (value: number): string => String(value).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function EventRow({ event, verbose }: { event: RunEvent; verbose: boolean }) {
  return (
    <li className={`event-row level-${event.level}`}>
      <time className="monospace" dateTime={event.timestamp}>{formatTime(event.timestamp)}</time>
      <span className="event-level">{event.level.toUpperCase()}</span>
      <span className="event-type monospace">{event.type}</span>
      <span className="event-node monospace">{event.node_id ?? '—'}</span>
      <span className="event-message">{event.message}</span>
      {verbose && event.data !== null && (
        <pre className="event-data">{JSON.stringify(event.data, null, 2)}</pre>
      )}
    </li>
  );
}

export function RunPanel({
  runs,
  run,
  events,
  streamStatus,
  collapsed,
  onToggleCollapsed,
  onSelectRun,
  onRefresh,
  onCancel,
  onResume,
  onApprove,
}: RunPanelProps) {
  const [tab, setTab] = useState<'timeline' | 'logs'>('timeline');
  const [showDetail, setShowDetail] = useState(false);
  const [note, setNote] = useState('');
  const [modifiedData, setModifiedData] = useState('{}');
  const selectedNodeId = useWorkflowStore((state) => state.selectedNodeId);
  const nodes = useWorkflowStore((state) => state.nodes);

  const nodeLabel = nodes.find((node) => node.id === selectedNodeId)?.data.label;
  const nodeState = run?.nodes.find((state) => state.node_id === selectedNodeId);

  const approve = (decision: ApprovalDecision): void => {
    if (decision === 'modify') {
      try {
        const data: unknown = JSON.parse(modifiedData);
        onApprove(decision, data, note);
      } catch {
        window.alert('El JSON de modificación no es válido');
        return;
      }
    } else {
      onApprove(decision, undefined, note);
    }
    setNote('');
  };

  return (
    <section className={`panel run-panel ${collapsed ? 'collapsed' : ''}`} aria-label="Panel de ejecución">
      <div className="panel-header run-header">
        <div className="run-header-left">
          <Activity size={15} aria-hidden="true" />
          <h2>Ejecución</h2>
          <span className={`stream-dot ${streamStatus}`} title={`SSE: ${streamStatus}`} />
          <span className="muted tiny">SSE {streamStatus}</span>
        </div>
        <div className="run-header-actions">
          <select
            aria-label="Seleccionar ejecución"
            value={run?.id ?? ''}
            onChange={(event) => onSelectRun(event.target.value)}
          >
            <option value="">— ninguna —</option>
            {runs.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id.slice(0, 8)} · {item.status}
              </option>
            ))}
          </select>
          <button type="button" className="icon-button" onClick={onRefresh} title="Refrescar" aria-label="Refrescar ejecución">
            <RotateCw size={14} />
          </button>
          <button
            type="button"
            className="button subtle small"
            onClick={() => setShowDetail((value) => !value)}
            aria-expanded={showDetail}
          >
            <Eye size={13} /> Detalle
          </button>
          {run && ACTIVE_STATUSES.includes(run.status) && (
            <button type="button" className="button subtle small" onClick={onCancel}>
              <Ban size={13} /> Cancelar
            </button>
          )}
          {run?.status === 'paused' && (
            <button type="button" className="button subtle small" onClick={onResume}>
              <PlayCircle size={13} /> Reanudar
            </button>
          )}
          <button
            type="button"
            className="icon-button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? 'Expandir panel' : 'Plegar panel'}
          >
            {collapsed ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          </button>
        </div>
      </div>

      {!collapsed && (
        <>
          <div className="run-summary">
            {run ? (
              <>
                <span className={`run-status status-${run.status}`}>{run.status}</span>
                <span className="muted tiny monospace">{run.id}</span>
                <span className="muted tiny">workflow {run.workflow_id.slice(0, 8)}</span>
                <span className="muted tiny">inicio {run.started_at ? formatTime(run.started_at) : '—'}</span>
                <span className="muted tiny">fin {run.finished_at ? formatTime(run.finished_at) : '—'}</span>
                {run.error && <span className="error-text">{run.error}</span>}
              </>
            ) : (
              <span className="muted small">Selecciona o crea una ejecución.</span>
            )}
          </div>

          {run?.approval && (
            <div className="approval-bar" role="alert">
              <PauseCircle size={16} aria-hidden="true" />
              <div>
                <strong>{run.approval.title || 'Aprobación requerida'}</strong>
                <small className="monospace">nodo {run.approval.node_id}</small>
                <pre>{JSON.stringify(run.approval.data, null, 2)}</pre>
              </div>
              <input
                aria-label="Nota de aprobación"
                value={note}
                placeholder="nota (opcional)"
                onChange={(event) => setNote(event.target.value)}
              />
              <input
                aria-label="Datos para modificar (JSON)"
                className="monospace"
                value={modifiedData}
                onChange={(event) => setModifiedData(event.target.value)}
                title='JSON usado por "Modificar"'
              />
              <button type="button" className="button small ok" onClick={() => approve('approve')}>
                <CircleCheck size={13} /> Aprobar
              </button>
              <button type="button" className="button small danger" onClick={() => approve('reject')}>
                <CircleX size={13} /> Rechazar
              </button>
              <button type="button" className="button subtle small" onClick={() => approve('modify')}>
                Modificar
              </button>
            </div>
          )}

          {showDetail && (
            <div className="node-detail">
              <div className="node-detail-title">
                <strong>Detalle del nodo</strong>
                <span className="muted tiny">{nodeLabel ?? selectedNodeId ?? '—'}</span>
              </div>
              {nodeState ? (
                <>
                  <div className="detail-line">
                    <span className={`status-badge status-${nodeState.status}`}>
                      <i className="status-dot" /> {nodeState.status}
                    </span>
                    <span className="muted tiny">intento {nodeState.attempts}</span>
                    <span className="muted tiny">iteración {nodeState.iteration}</span>
                    <span className="muted tiny">{nodeState.duration_ms ?? '—'} ms</span>
                    <span className="muted tiny">runtime {nodeState.runtime ?? '—'}</span>
                    {nodeState.simulated && <span className="sim-tag">SIMULADO</span>}
                  </div>
                  {nodeState.error && <pre className="detail-error">{nodeState.error}</pre>}
                  <div className="detail-columns">
                    <div>
                      <h3>Input</h3>
                      <pre>{JSON.stringify(nodeState.input, null, 2)}</pre>
                    </div>
                    <div>
                      <h3>Output</h3>
                      <pre>{JSON.stringify(nodeState.output, null, 2)}</pre>
                    </div>
                  </div>
                </>
              ) : (
                <p className="muted small">Sin estado para el nodo seleccionado.</p>
              )}
              {run?.outputs !== null && run?.outputs !== undefined && (
                <details>
                  <summary>Outputs del workflow</summary>
                  <pre>{JSON.stringify(run.outputs, null, 2)}</pre>
                </details>
              )}
            </div>
          )}

          <div className="run-tabs" role="tablist" aria-label="Vistas de ejecución">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'timeline'}
              className={tab === 'timeline' ? 'active' : ''}
              onClick={() => setTab('timeline')}
            >
              <ScrollText size={13} /> Timeline
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'logs'}
              className={tab === 'logs' ? 'active' : ''}
              onClick={() => setTab('logs')}
            >
              <Activity size={13} /> Logs
            </button>
            <span className="muted tiny">{events.length} eventos</span>
          </div>
          <div className="event-scroll" role="tabpanel">
            {events.length === 0 ? (
              <p className="muted small event-empty">
                {TERMINAL_STATUSES.includes(run?.status ?? 'created')
                  ? 'Sin eventos para esta ejecución.'
                  : 'Esperando eventos del stream…'}
              </p>
            ) : (
              <ul className="event-list">
                {[...events].reverse().map((event) => (
                  <EventRow key={event.id || `${event.seq}-${event.run_id}`} event={event} verbose={tab === 'logs'} />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}
