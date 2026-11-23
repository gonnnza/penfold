import { useState, type FormEvent } from 'react';
import {
  AlertTriangle,
  Check,
  CirclePlay,
  Loader2,
  Plus,
  Save,
  ShieldCheck,
  Workflow as WorkflowIcon,
} from 'lucide-react';
import { ApiError, createRun, saveWorkflow, validateWorkflow } from '../api';
import { demoWorkflow, useWorkflowStore, workflowToDefinition } from '../store';
import type {
  AppConfig,
  RunDetail,
  ValidationIssue,
  WorkflowSummary,
} from '../types';

export type ConnectionState = 'checking' | 'online' | 'offline';

interface TopbarProps {
  config: AppConfig | null;
  workflows: WorkflowSummary[];
  connection: ConnectionState;
  onSelectWorkflow: (id: string) => void;
  onWorkflowsChanged: () => Promise<void>;
  onRunCreated: (run: RunDetail) => void;
  onIssues: (issues: ValidationIssue[]) => void;
}

function stringifyInput(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

export function Topbar({
  config,
  workflows,
  connection,
  onSelectWorkflow,
  onWorkflowsChanged,
  onRunCreated,
  onIssues,
}: TopbarProps) {
  const metadata = useWorkflowStore((state) => state.metadata);
  const inputs = useWorkflowStore((state) => state.inputs);
  const dirty = useWorkflowStore((state) => state.dirty);
  const saving = useWorkflowStore((state) => state.saving);
  const ensureWorkflowId = useWorkflowStore((state) => state.ensureWorkflowId);
  const newWorkflow = useWorkflowStore((state) => state.newWorkflow);
  const loadWorkflow = useWorkflowStore((state) => state.loadWorkflow);
  const setSaving = useWorkflowStore((state) => state.setSaving);
  const markSaved = useWorkflowStore((state) => state.markSaved);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [inputValues, setInputValues] = useState<Record<string, string>>({});

  const reportError = (err: unknown): void => {
    setError(err instanceof ApiError ? err.detail : String(err));
  };

  const handleNew = (): void => {
    if (dirty && !window.confirm('Descartar los cambios sin guardar?')) return;
    newWorkflow();
    onIssues([]);
    setError(null);
  };

  const handleSave = async (): Promise<void> => {
    setSaving(true);
    setError(null);
    try {
      ensureWorkflowId();
      const result = await saveWorkflow(
        workflowToDefinition({
          nodes: useWorkflowStore.getState().nodes,
          edges: useWorkflowStore.getState().edges,
          metadata: useWorkflowStore.getState().metadata,
          inputs: useWorkflowStore.getState().inputs,
        }),
      );
      markSaved();
      onIssues(result.issues);
      await onWorkflowsChanged();
    } catch (err) {
      reportError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      ensureWorkflowId();
      const current = useWorkflowStore.getState();
      const result = await validateWorkflow(workflowToDefinition(current));
      onIssues(result.issues);
    } catch (err) {
      reportError(err);
    } finally {
      setBusy(false);
    }
  };

  const startRun = async (values: Record<string, unknown>): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const hadId = Boolean(metadata.id);
      const id = ensureWorkflowId();
      if (dirty || !hadId) {
        const current = useWorkflowStore.getState();
        await saveWorkflow(workflowToDefinition(current));
        markSaved();
        await onWorkflowsChanged();
      }
      const run = await createRun(id, values);
      setShowModal(false);
      onRunCreated(run);
    } catch (err) {
      reportError(err);
    } finally {
      setBusy(false);
    }
  };

  const handleRun = (): void => {
    const missing = inputs.filter(
      (input) => input.required === true && !stringifyInput(input.default),
    );
    if (missing.length > 0) {
      setInputValues(
        Object.fromEntries(inputs.map((input) => [input.id, stringifyInput(input.default)])),
      );
      setShowModal(true);
      return;
    }
    const values = Object.fromEntries(
      inputs.map((input) => [input.id, input.default ?? '']),
    );
    void startRun(values);
  };

  const submitModal = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const values: Record<string, unknown> = {};
    for (const input of inputs) {
      const raw = inputValues[input.id] ?? '';
      if (input.type === 'number') values[input.id] = raw === '' ? null : Number(raw);
      else if (input.type === 'boolean') values[input.id] = raw === 'true';
      else values[input.id] = raw;
    }
    void startRun(values);
  };

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <WorkflowIcon size={19} strokeWidth={2} aria-hidden="true" />
          <strong>Penfold</strong>
          <span className="brand-sub">visual orchestrator</span>
        </div>

        <div className="project-name" title={config?.project.description}>
          {config?.project.name ?? 'proyecto local'}
        </div>

        <label className="workflow-select">
          <span className="sr-only">Workflow</span>
          <select
            value={metadata.id}
            onChange={(event) => onSelectWorkflow(event.target.value)}
            aria-label="Seleccionar workflow"
          >
            <option value="">— sin workflow guardado —</option>
            {workflows.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
        </label>

        <div className="topbar-actions">
          <button type="button" className="button subtle" onClick={handleNew} title="Nuevo workflow">
            <Plus size={15} /> Nuevo
          </button>
          <button
            type="button"
            className="button subtle"
            onClick={() => loadWorkflow(demoWorkflow())}
            title="Cargar workflow de ejemplo (input → agent → output)"
          >
            Demo
          </button>
          <button
            type="button"
            className="button subtle"
            onClick={() => void handleSave()}
            disabled={saving}
            title="Guardar workflow (PUT)"
          >
            {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />} Guardar
          </button>
          <button
            type="button"
            className="button subtle"
            onClick={() => void handleValidate()}
            disabled={busy}
            title="Validar workflow"
          >
            <ShieldCheck size={15} /> Validar
          </button>
          <button type="button" className="button primary" onClick={handleRun} disabled={busy}>
            <CirclePlay size={15} /> Ejecutar
          </button>
        </div>

        <div className="topbar-status" aria-live="polite">
          <span
            className={`connection-dot ${connection}`}
            title={`API: ${connection}`}
            aria-label={`Conexión: ${connection}`}
          />
          <span className={dirty ? 'dirty' : 'saved'}>
            {saving ? (
              <>
                <Loader2 size={12} className="spin" /> guardando
              </>
            ) : dirty ? (
              <>
                <AlertTriangle size={12} /> sin guardar
              </>
            ) : (
              <>
                <Check size={12} /> guardado
              </>
            )}
          </span>
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <AlertTriangle size={14} /> {error}
          <button type="button" className="icon-button" aria-label="Cerrar error" onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}

      {showModal && (
        <div className="modal-backdrop" role="presentation">
          <form className="modal" role="dialog" aria-modal="true" aria-labelledby="run-inputs-title" onSubmit={submitModal}>
            <h2 id="run-inputs-title">Inputs de la ejecución</h2>
            <p className="muted small">Completa los valores requeridos antes de ejecutar.</p>
            {inputs.map((input) => (
              <div className="field" key={input.id}>
                <label htmlFor={`run-${input.id}`}>
                  {input.id} <span className="muted tiny">({input.type}{input.required ? ', requerido' : ''})</span>
                </label>
                <input
                  id={`run-${input.id}`}
                  value={inputValues[input.id] ?? ''}
                  onChange={(event) =>
                    setInputValues((prev) => ({ ...prev, [input.id]: event.target.value }))
                  }
                  required={input.required}
                />
              </div>
            ))}
            <div className="modal-actions">
              <button type="button" className="button subtle" onClick={() => setShowModal(false)}>
                Cancelar
              </button>
              <button type="submit" className="button primary" disabled={busy}>
                {busy ? <Loader2 size={14} className="spin" /> : <CirclePlay size={14} />} Ejecutar
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
