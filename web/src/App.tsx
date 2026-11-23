import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { KeyRound, Loader2 } from 'lucide-react';
import {
  ApiError,
  approveRun,
  cancelRun,
  checkToken,
  consumeTokenFromUrl,
  getConfig,
  getEventsAfter,
  getHealth,
  getRun,
  getToken,
  getWorkflow,
  listAgents,
  listRuns,
  listWorkflows,
  onUnauthorized,
  resumeRun,
  saveWorkflow,
  subscribeRunEvents,
} from './api';
import { Inspector } from './components/Inspector';
import { NodeLibrary } from './components/NodeLibrary';
import { RunPanel } from './components/RunPanel';
import { Topbar, type ConnectionState } from './components/Topbar';
import { WorkflowCanvas } from './components/WorkflowCanvas';
import { useWorkflowStore, workflowToDefinition } from './store';
import type {
  AgentDefinition,
  AppConfig,
  ApprovalDecision,
  RunDetail,
  RunEvent,
  RunSummary,
  NodeType,
  ValidationIssue,
  WorkflowSummary,
} from './types';

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : String(error);
}

function TokenGate({ reason, onToken }: { reason: string | null; onToken: (token: string) => Promise<void> }) {
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!draft.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onToken(draft.trim());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="token-gate">
      <form className="token-card" onSubmit={(event) => void submit(event)}>
        <div className="token-logo"><KeyRound size={22} aria-hidden="true" /></div>
        <h1>Penfold</h1>
        <p className="muted small">
          Orquestador visual local-first. Introduce el token mostrado por el servidor local para
          continuar. Se guarda sólo en este navegador (<code>localStorage</code>).
        </p>
        {reason && <div className="mock-warning">{reason}</div>}
        <label htmlFor="token-input">Token de Penfold</label>
        <input
          id="token-input"
          className="monospace"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          autoFocus
          autoComplete="off"
        />
        {error && <div className="error-text" role="alert">{error}</div>}
        <button type="submit" className="button primary" disabled={busy || !draft.trim()}>
          {busy ? <Loader2 size={15} className="spin" /> : <KeyRound size={15} />} Conectar
        </button>
      </form>
    </div>
  );
}

export default function App() {
  const [token, setTokenState] = useState<string | null>(() => consumeTokenFromUrl());
  const [tokenReason, setTokenReason] = useState<string | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [agents, setAgentList] = useState<AgentDefinition[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [connection, setConnection] = useState<ConnectionState>('checking');
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [streamStatus, setStreamStatus] = useState<'idle' | 'connected' | 'reconnecting'>('idle');
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [autoSaveError, setAutoSaveError] = useState<string | null>(null);

  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const metadata = useWorkflowStore((state) => state.metadata);
  const inputs = useWorkflowStore((state) => state.inputs);
  const dirty = useWorkflowStore((state) => state.dirty);
  const saving = useWorkflowStore((state) => state.saving);

  const definition = useMemo(
    () => workflowToDefinition({ nodes, edges, metadata, inputs }),
    [nodes, edges, metadata, inputs],
  );
  const payload = JSON.stringify(definition);

  const loadRuns = useCallback(async (): Promise<void> => {
    try {
      setRuns(await listRuns({ limit: 50 }));
    } catch {
      // El banner de conexión ya informa del fallo.
    }
  }, []);

  const refreshWorkflows = useCallback(async (): Promise<void> => {
    try {
      setWorkflows(await listWorkflows());
    } catch {
      // Silencioso: se reintentará con el health-check.
    }
  }, []);

  useEffect(() => onUnauthorized(() => {
    setTokenState(null);
    setTokenReason('El token no es válido o ha caducado. Vuelve a introducirlo.');
  }), []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    const load = async (): Promise<void> => {
      try {
        const [configResult, workflowList, agentList] = await Promise.all([
          getConfig(),
          listWorkflows(),
          listAgents(),
        ]);
        if (cancelled) return;
        setConfig(configResult);
        setWorkflows(workflowList);
        setAgentList(agentList);
        useWorkflowStore.getState().setAgents(agentList);
        await loadRuns();
        const store = useWorkflowStore.getState();
        if (workflowList.length > 0 && !store.metadata.id && store.nodes.length === 0) {
          const first = await getWorkflow(workflowList[0].id);
          if (!cancelled) useWorkflowStore.getState().loadWorkflow(first);
        }
      } catch (error) {
        if (!cancelled) setAutoSaveError(errorMessage(error));
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [token, loadRuns]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const check = async (): Promise<void> => {
      try {
        await getHealth();
        if (!cancelled) setConnection('online');
      } catch {
        if (!cancelled) setConnection('offline');
      }
    };
    void check();
    const timer = setInterval(() => void check(), 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [token]);

  useEffect(() => {
    const handler = (event: KeyboardEvent): void => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
      ) {
        return;
      }
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && key === 'z') {
        event.preventDefault();
        if (event.shiftKey) useWorkflowStore.getState().redo();
        else useWorkflowStore.getState().undo();
      } else if ((event.ctrlKey || event.metaKey) && key === 'y') {
        event.preventDefault();
        useWorkflowStore.getState().redo();
      } else if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        useWorkflowStore.getState().deleteSelection();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Guardado automático silencioso (debounce ~800 ms).
  useEffect(() => {
    if (!token || !dirty || !metadata.id || saving) return;
    const timer = setTimeout(() => {
      const store = useWorkflowStore.getState();
      store.setSaving(true);
      void saveWorkflow(workflowToDefinition(store))
        .then((result) => {
          useWorkflowStore.getState().markSaved();
          setIssues(result.issues);
          setAutoSaveError(null);
          void refreshWorkflows();
        })
        .catch((error: unknown) => setAutoSaveError(errorMessage(error)))
        .finally(() => useWorkflowStore.getState().setSaving(false));
    }, 800);
    return () => clearTimeout(timer);
  }, [token, dirty, metadata.id, payload, saving, refreshWorkflows]);

  // Stream SSE + polling del detalle del run.
  useEffect(() => {
    if (!token || !activeRunId) return;
    let cancelled = false;
    const id = activeRunId;

    void getEventsAfter(id, 0)
      .then((previous) => {
        if (!cancelled) {
          setEvents((current) => {
            const seen = new Set(current.map((event) => event.id));
            return [...current, ...previous.filter((event) => !seen.has(event.id))];
          });
        }
      })
      .catch(() => {});

    const unsubscribe = subscribeRunEvents(
      id,
      0,
      (event) => {
        if (cancelled) return;
        setEvents((current) =>
          current.some((item) => item.id === event.id) ? current : [...current, event],
        );
      },
      () => setStreamStatus('reconnecting'),
    );
    setStreamStatus('connected');

    const poll = async (): Promise<void> => {
      try {
        const detail = await getRun(id);
        if (cancelled) return;
        setRun(detail);
        useWorkflowStore.getState().setNodeStates(detail.nodes);
        void loadRuns();
      } catch {
        // Se reintentará en el siguiente ciclo.
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);

    return () => {
      cancelled = true;
      unsubscribe();
      clearInterval(timer);
      setStreamStatus('idle');
    };
  }, [token, activeRunId, loadRuns]);

  const handleToken = async (value: string): Promise<void> => {
    await checkToken({ token: value, url: '' });
    setTokenState(getToken());
    setTokenReason(null);
  };

  const handleSelectWorkflow = async (id: string): Promise<void> => {
    setActiveRunId(null);
    setRun(null);
    setEvents([]);
    setIssues([]);
    if (!id) {
      useWorkflowStore.getState().newWorkflow();
      return;
    }
    try {
      useWorkflowStore.getState().loadWorkflow(await getWorkflow(id));
    } catch (error) {
      setAutoSaveError(errorMessage(error));
    }
  };

  const handleRunCreated = (created: RunDetail): void => {
    setActiveRunId(created.id);
    setRun(created);
    setEvents([]);
    setPanelCollapsed(false);
    useWorkflowStore.getState().setNodeStates(created.nodes);
    void loadRuns();
  };

  const refreshRun = async (): Promise<void> => {
    if (!activeRunId) return;
    try {
      const detail = await getRun(activeRunId);
      setRun(detail);
      useWorkflowStore.getState().setNodeStates(detail.nodes);
    } catch (error) {
      setAutoSaveError(errorMessage(error));
    }
  };

  const handleApprove = async (
    decision: ApprovalDecision,
    data?: unknown,
    note?: string,
  ): Promise<void> => {
    if (!activeRunId) return;
    try {
      await approveRun(activeRunId, decision, data, note);
      await refreshRun();
      await loadRuns();
    } catch (error) {
      setAutoSaveError(errorMessage(error));
    }
  };

  const handleCancel = async (): Promise<void> => {
    if (!activeRunId) return;
    try {
      await cancelRun(activeRunId);
      await refreshRun();
      await loadRuns();
    } catch (error) {
      setAutoSaveError(errorMessage(error));
    }
  };

  const handleResume = async (): Promise<void> => {
    if (!activeRunId) return;
    try {
      await resumeRun(activeRunId);
      await refreshRun();
      await loadRuns();
    } catch (error) {
      setAutoSaveError(errorMessage(error));
    }
  };

  const handleAddNode = (type: NodeType): void => {
    const count = useWorkflowStore.getState().nodes.length;
    useWorkflowStore.getState().addNode(type, {
      x: 80 + (count % 3) * 250,
      y: 80 + Math.floor(count / 3) * 150,
    });
  };

  if (!token) {
    return <TokenGate reason={tokenReason} onToken={handleToken} />;
  }

  return (
    <div className="app">
      <Topbar
        config={config}
        workflows={workflows}
        connection={connection}
        onSelectWorkflow={(id) => void handleSelectWorkflow(id)}
        onWorkflowsChanged={refreshWorkflows}
        onRunCreated={handleRunCreated}
        onIssues={setIssues}
      />

      {(autoSaveError || connection === 'offline') && (
        <div className="error-banner" role="status">
          {autoSaveError ?? 'Servidor no disponible. Reintentando conexión…'}
          {autoSaveError && (
            <button type="button" className="icon-button" aria-label="Cerrar aviso" onClick={() => setAutoSaveError(null)}>
              ×
            </button>
          )}
        </div>
      )}

      <div className="workspace">
        <NodeLibrary onAdd={handleAddNode} />
        <ReactFlowProvider>
          <WorkflowCanvas />
        </ReactFlowProvider>
        <Inspector agents={agents} issues={issues} />
      </div>

      <RunPanel
        runs={runs}
        run={run}
        events={events}
        streamStatus={streamStatus}
        collapsed={panelCollapsed}
        onToggleCollapsed={() => setPanelCollapsed((value) => !value)}
        onSelectRun={(id) => {
          setActiveRunId(id || null);
          setRun(null);
          setEvents([]);
        }}
        onRefresh={() => void refreshRun()}
        onCancel={() => void handleCancel()}
        onResume={() => void handleResume()}
        onApprove={(decision, data, note) => void handleApprove(decision, data, note)}
      />
    </div>
  );
}
