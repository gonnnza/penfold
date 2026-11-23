import { AlertTriangle, FlaskConical, Info, Plus, Trash2 } from 'lucide-react';
import { CONDITION_OPS, NODE_META } from '../nodeMeta';
import { useWorkflowStore, type PenfoldFlowNode } from '../store';
import type { AgentDefinition, InputMapping, ValidationIssue, WorkflowInput } from '../types';
import { NODE_ICONS } from './NodeLibrary';

interface InspectorProps {
  agents: AgentDefinition[];
  issues: ValidationIssue[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function str(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function num(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asMapping(value: unknown): InputMapping {
  return isRecord(value) ? value : {};
}

interface MappingEditorProps {
  value: InputMapping;
  onChange: (mapping: InputMapping) => void;
  label?: string;
}

function MappingEditor({ value, onChange, label = 'Mapeo de entradas' }: MappingEditorProps) {
  const entries = Object.entries(value);
  return (
    <fieldset className="field-group">
      <legend>{label}</legend>
      <p className="hint">
        Expresiones: <code>$inputs.nombre</code>, <code>$nodes.id.output.campo</code> o literales.
      </p>
      {entries.map(([key, expression], index) => (
        <div className="mapping-row" key={`${key}-${index}`}>
          <input
            aria-label={`Clave de entrada ${index + 1}`}
            value={key}
            onChange={(event) => {
              const next: InputMapping = {};
              for (const [k, v] of entries) next[k === key ? event.target.value : k] = v;
              onChange(next);
            }}
          />
          <input
            aria-label={`Expresión para ${key}`}
            value={str(expression)}
            placeholder="$inputs.tema"
            onChange={(event) => onChange({ ...value, [key]: event.target.value })}
          />
          <button
            type="button"
            className="icon-button danger"
            aria-label={`Quitar mapeo ${key}`}
            onClick={() => {
              const next = { ...value };
              delete next[key];
              onChange(next);
            }}
          >
            <Trash2 size={13} />
          </button>
        </div>
      ))}
      <button
        type="button"
        className="button subtle small"
        onClick={() => {
          let index = entries.length + 1;
          let key = `campo${index}`;
          while (key in value) {
            index += 1;
            key = `campo${index}`;
          }
          onChange({ ...value, [key]: '' });
        }}
      >
        <Plus size={13} /> Añadir entrada
      </button>
    </fieldset>
  );
}

function NumberField({
  id,
  label,
  value,
  min = 0,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  min?: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        min={min}
        value={value}
        onChange={(event) => onChange(Math.max(min, num(event.target.value, min)))}
      />
    </div>
  );
}

function WorkflowSettings({ issues }: { issues: ValidationIssue[] }) {
  const metadata = useWorkflowStore((state) => state.metadata);
  const inputs = useWorkflowStore((state) => state.inputs);
  const setMetadata = useWorkflowStore((state) => state.setMetadata);
  const setInputs = useWorkflowStore((state) => state.setInputs);

  const patchInput = (index: number, patch: Partial<WorkflowInput>): void => {
    setInputs(inputs.map((input, i) => (i === index ? { ...input, ...patch } : input)));
  };

  return (
    <div className="inspector-body">
      <div className="inspector-intro">
        <Info size={14} /> Ningún nodo seleccionado. Configura el workflow o selecciona un nodo.
      </div>
      <div className="field">
        <label htmlFor="wf-name">Nombre del workflow</label>
        <input
          id="wf-name"
          value={metadata.name}
          onChange={(event) => setMetadata({ name: event.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="wf-id">ID</label>
        <input id="wf-id" className="monospace" value={metadata.id} readOnly />
      </div>
      <div className="field">
        <label htmlFor="wf-description">Descripción</label>
        <textarea
          id="wf-description"
          rows={2}
          value={metadata.description ?? ''}
          onChange={(event) => setMetadata({ description: event.target.value })}
        />
      </div>

      <fieldset className="field-group">
        <legend>Inputs del workflow</legend>
        {inputs.map((input, index) => (
          <div className="input-row" key={`${input.id}-${index}`}>
            <input
              aria-label={`ID del input ${index + 1}`}
              className="monospace"
              value={input.id}
              onChange={(event) => patchInput(index, { id: event.target.value })}
            />
            <input
              aria-label={`Tipo del input ${index + 1}`}
              value={input.type}
              placeholder="string"
              onChange={(event) => patchInput(index, { type: event.target.value })}
            />
            <label className="checkbox-label" title="Requerido">
              <input
                type="checkbox"
                checked={input.required === true}
                onChange={(event) => patchInput(index, { required: event.target.checked })}
              />
              req.
            </label>
            <button
              type="button"
              className="icon-button danger"
              aria-label={`Eliminar input ${input.id}`}
              onClick={() => setInputs(inputs.filter((_, i) => i !== index))}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
        <button
          type="button"
          className="button subtle small"
          onClick={() =>
            setInputs([...inputs, { id: `input${inputs.length + 1}`, type: 'string', required: false }])
          }
        >
          <Plus size={13} /> Añadir input
        </button>
      </fieldset>

      {issues.length > 0 && (
        <fieldset className="field-group">
          <legend>Última validación</legend>
          <ul className="issue-list">
            {issues.map((issue, index) => (
              <li key={`${issue.path}-${index}`} className={`issue ${issue.severity}`}>
                <AlertTriangle size={12} aria-hidden="true" />
                <span>
                  <code>{issue.path}</code> {issue.message}
                </span>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
    </div>
  );
}

function NodeInspector({ node, agents }: { node: PenfoldFlowNode; agents: AgentDefinition[] }) {
  const updateNodeConfig = useWorkflowStore((state) => state.updateNodeConfig);
  const updateNodeData = useWorkflowStore((state) => state.updateNodeData);
  const simulated = useWorkflowStore((state) => state.nodeStates[node.id]?.simulated ?? false);

  const config = node.data.config;
  const type = node.data.nodeType;
  const Icon = NODE_ICONS[type];
  const agent = agents.find((item) => item.id === node.data.agent);
  const agentMock = agent?.runtime.type === 'mock' || node.data.mockRuntime;
  const showMockWarning = agentMock || simulated;

  const patchConfig = (patch: Record<string, unknown>): void => updateNodeConfig(node.id, patch);

  return (
    <div className="inspector-body">
      <div className="inspector-title">
        <span className={`library-icon node-${type}`}>
          <Icon size={16} aria-hidden="true" />
        </span>
        <div>
          <strong>{node.data.label}</strong>
          <small>{NODE_META[type].label}</small>
        </div>
      </div>

      {showMockWarning && (
        <div className="mock-warning" role="status">
          <FlaskConical size={14} aria-hidden="true" />
          <span>
            SIMULADO — MockRuntime
            <small>
              {simulated
                ? 'Esta salida provino de una ejecución simulada; no es una ejecución real.'
                : 'El agente seleccionado usa MockRuntime. La ejecución producirá datos simulados.'}
            </small>
          </span>
        </div>
      )}

      <fieldset className="field-group">
        <legend>General</legend>
        <div className="field">
          <label htmlFor="node-label">Nombre</label>
          <input
            id="node-label"
            value={node.data.label}
            onChange={(event) => updateNodeData(node.id, { label: event.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="node-id">ID</label>
          <input id="node-id" className="monospace" value={node.id} readOnly />
        </div>
        <div className="field">
          <label htmlFor="node-description">Descripción</label>
          <textarea
            id="node-description"
            rows={2}
            value={node.data.description}
            onChange={(event) => updateNodeData(node.id, { description: event.target.value })}
          />
        </div>
      </fieldset>

      {type === 'agent' && (
        <>
          <fieldset className="field-group">
            <legend>Agente</legend>
            <div className="field">
              <label htmlFor="agent-select">Definición</label>
              <select
                id="agent-select"
                value={node.data.agent ?? ''}
                onChange={(event) => updateNodeData(node.id, { agent: event.target.value || null })}
              >
                <option value="">— seleccionar agente —</option>
                {agents.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="agent-instructions">Instrucciones (solo lectura)</label>
              <textarea
                id="agent-instructions"
                className="readonly"
                rows={5}
                value={agent?.instructions ?? 'Selecciona un agente para ver sus instrucciones.'}
                readOnly
              />
            </div>
            <div className="runtime-grid">
              <div>
                <span className="muted tiny">Runtime</span>
                <strong className="monospace">{agent?.runtime.type ?? '—'}</strong>
              </div>
              <div>
                <span className="muted tiny">Proveedor</span>
                <strong className="monospace">{agent?.runtime.provider ?? '—'}</strong>
              </div>
              <div>
                <span className="muted tiny">Modelo</span>
                <strong className="monospace">{agent?.runtime.model ?? '—'}</strong>
              </div>
            </div>
            <NumberField
              id="agent-timeout"
              label="Timeout (s)"
              value={num(config.timeout, agent?.timeout ?? 30)}
              min={1}
              onChange={(value) => patchConfig({ timeout: value })}
            />
            <NumberField
              id="agent-retries"
              label="Reintentos"
              value={num(config.retries, agent?.retries ?? 0)}
              onChange={(value) => patchConfig({ retries: value })}
            />
            <div className="field">
              <label htmlFor="agent-context">Contexto (una ruta por línea)</label>
              <textarea
                id="agent-context"
                rows={3}
                className="monospace"
                value={Array.isArray(config.context) ? config.context.join('\n') : ''}
                onChange={(event) =>
                  patchConfig({ context: event.target.value.split('\n').filter(Boolean) })
                }
              />
            </div>
          </fieldset>
          <MappingEditor
            value={asMapping(config.inputs)}
            onChange={(mapping) => patchConfig({ inputs: mapping })}
          />
        </>
      )}

      {type === 'command' && (
        <>
          <fieldset className="field-group">
            <legend>Command</legend>
            <div className="field">
              <label htmlFor="cmd-command">Comando (shlex, sin shell)</label>
              <input
                id="cmd-command"
                className="monospace"
                value={str(config.command)}
                placeholder="python -m pytest -q"
                onChange={(event) => patchConfig({ command: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="cmd-cwd">Directorio de trabajo</label>
              <input
                id="cmd-cwd"
                className="monospace"
                value={str(config.cwd, '.')}
                onChange={(event) => patchConfig({ cwd: event.target.value })}
              />
            </div>
            <NumberField
              id="cmd-timeout"
              label="Timeout (s)"
              value={num(config.timeout, 30)}
              min={1}
              onChange={(value) => patchConfig({ timeout: value })}
            />
          </fieldset>
          <MappingEditor
            value={asMapping(config.inputs)}
            onChange={(mapping) => patchConfig({ inputs: mapping })}
          />
        </>
      )}

      {type === 'condition' && (
        <>
          <fieldset className="field-group">
            <legend>Condición</legend>
            <div className="field">
              <label htmlFor="cond-field">Campo</label>
              <input
                id="cond-field"
                className="monospace"
                value={str(isRecord(config.expression) ? config.expression.field : '')}
                onChange={(event) =>
                  patchConfig({
                    expression: {
                      ...(isRecord(config.expression) ? config.expression : {}),
                      field: event.target.value,
                    },
                  })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="cond-op">Operador</label>
              <select
                id="cond-op"
                value={str(isRecord(config.expression) ? config.expression.op : 'eq', 'eq')}
                onChange={(event) =>
                  patchConfig({
                    expression: {
                      ...(isRecord(config.expression) ? config.expression : {}),
                      op: event.target.value,
                    },
                  })
                }
              >
                {CONDITION_OPS.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="cond-value">Valor</label>
              <input
                id="cond-value"
                className="monospace"
                value={str(isRecord(config.expression) ? config.expression.value : '')}
                onChange={(event) =>
                  patchConfig({
                    expression: {
                      ...(isRecord(config.expression) ? config.expression : {}),
                      value: event.target.value,
                    },
                  })
                }
              />
            </div>
          </fieldset>
          <MappingEditor
            value={asMapping(config.inputs)}
            onChange={(mapping) => patchConfig({ inputs: mapping })}
          />
        </>
      )}

      {type === 'approval' && (
        <>
          <fieldset className="field-group">
            <legend>Approval</legend>
            <div className="field">
              <label htmlFor="appr-title">Título</label>
              <input
                id="appr-title"
                value={str(config.title)}
                onChange={(event) => patchConfig({ title: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="appr-message">Mensaje</label>
              <textarea
                id="appr-message"
                rows={4}
                value={str(config.message)}
                onChange={(event) => patchConfig({ message: event.target.value })}
              />
            </div>
          </fieldset>
          <MappingEditor
            value={asMapping(config.inputs)}
            onChange={(mapping) => patchConfig({ inputs: mapping })}
          />
        </>
      )}

      {type === 'output' && (
        <>
          <fieldset className="field-group">
            <legend>Output</legend>
            <div className="field">
              <label htmlFor="out-format">Formato</label>
              <select
                id="out-format"
                value={str(config.format, 'json')}
                onChange={(event) => patchConfig({ format: event.target.value })}
              >
                <option value="json">json</option>
                <option value="summary">summary</option>
              </select>
            </div>
          </fieldset>
          <MappingEditor
            value={asMapping(config.inputs)}
            onChange={(mapping) => patchConfig({ inputs: mapping })}
          />
        </>
      )}

      {type === 'input' && (
        <div className="inspector-intro">
          <Info size={14} /> Las entradas se declaran en el workflow. Selecciona el fondo del canvas
          para editarlas.
        </div>
      )}
    </div>
  );
}

export function Inspector({ agents, issues }: InspectorProps) {
  const selectedNodeId = useWorkflowStore((state) => state.selectedNodeId);
  const node = useWorkflowStore((state) =>
    state.nodes.find((item) => item.id === state.selectedNodeId),
  );

  return (
    <aside className="panel inspector" aria-label="Inspector">
      <div className="panel-header">
        <h2>Inspector</h2>
        {selectedNodeId && <span className="muted tiny monospace">{selectedNodeId.slice(-8)}</span>}
      </div>
      {node ? <NodeInspector node={node} agents={agents} /> : <WorkflowSettings issues={issues} />}
    </aside>
  );
}
