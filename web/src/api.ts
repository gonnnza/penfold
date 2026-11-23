import type {
  AgentDefinition,
  AppConfig,
  ApprovalDecision,
  HealthStatus,
  RunDetail,
  RunEvent,
  RunSummary,
  TokenInfo,
  ValidationResult,
  WorkflowDefinition,
  WorkflowSummary,
} from './types';

export const TOKEN_KEY = 'penfold.token';
const API_BASE = '/api';
const UNAUTHORIZED_EVENT = 'penfold:unauthorized';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/** Se lanza en 401. La App muestra la pantalla de token al recibirla. */
export class TokenRequiredError extends Error {
  constructor() {
    super('Se requiere un token de Penfold');
    this.name = 'TokenRequiredError';
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token.trim());
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function onUnauthorized(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(UNAUTHORIZED_EVENT, listener);
  return () => window.removeEventListener(UNAUTHORIZED_EVENT, listener);
}

function signalUnauthorized(): void {
  clearToken();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { 'X-Penfold-Token': token } : {};
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = options;
  const headers: Record<string, string> = { ...authHeaders() };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    throw new ApiError(0, `No se pudo conectar con el servidor: ${String(error)}`);
  }

  if (response.status === 401) {
    signalUnauthorized();
    throw new TokenRequiredError();
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : typeof payload === 'string'
          ? payload
          : response.statusText || `HTTP ${response.status}`;
    throw new ApiError(response.status, detail);
  }

  return payload as T;
}

// ---------------------------------------------------------------------------
// Sistema
// ---------------------------------------------------------------------------

export function getHealth(signal?: AbortSignal): Promise<HealthStatus> {
  return request<HealthStatus>('/health', { signal });
}

export function getConfig(signal?: AbortSignal): Promise<AppConfig> {
  return request<AppConfig>('/config', { signal });
}

// ---------------------------------------------------------------------------
// Workflows
// ---------------------------------------------------------------------------

export function listWorkflows(signal?: AbortSignal): Promise<WorkflowSummary[]> {
  return request<WorkflowSummary[]>('/workflows', { signal });
}

export function getWorkflow(id: string, signal?: AbortSignal): Promise<WorkflowDefinition> {
  return request<WorkflowDefinition>(`/workflows/${encodeURIComponent(id)}`, { signal });
}

export interface SaveWorkflowResult {
  ok: boolean;
  id: string;
  issues: ValidationResult['issues'];
}

export function saveWorkflow(
  definition: WorkflowDefinition,
  signal?: AbortSignal,
): Promise<SaveWorkflowResult> {
  return request<SaveWorkflowResult>(`/workflows/${encodeURIComponent(definition.metadata.id)}`, {
    method: 'PUT',
    body: definition,
    signal,
  });
}

export function validateWorkflow(
  definition: WorkflowDefinition,
  signal?: AbortSignal,
): Promise<ValidationResult> {
  return request<ValidationResult>('/workflows/validate', {
    method: 'POST',
    body: definition,
    signal,
  });
}

export function deleteWorkflow(id: string, signal?: AbortSignal): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/workflows/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    signal,
  });
}

// ---------------------------------------------------------------------------
// Agentes
// ---------------------------------------------------------------------------

export function listAgents(signal?: AbortSignal): Promise<AgentDefinition[]> {
  return request<AgentDefinition[]>('/agents', { signal });
}

export function getAgent(id: string, signal?: AbortSignal): Promise<AgentDefinition> {
  return request<AgentDefinition>(`/agents/${encodeURIComponent(id)}`, { signal });
}

export function saveAgent(
  agent: AgentDefinition,
  signal?: AbortSignal,
): Promise<{ ok: boolean; id: string }> {
  return request<{ ok: boolean; id: string }>(`/agents/${encodeURIComponent(agent.id)}`, {
    method: 'PUT',
    body: agent,
    signal,
  });
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export function listRuns(
  params: { workflow_id?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<RunSummary[]> {
  const query = new URLSearchParams();
  if (params.workflow_id) query.set('workflow_id', params.workflow_id);
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  const suffix = query.toString();
  return request<RunSummary[]>(`/runs${suffix ? `?${suffix}` : ''}`, { signal });
}

export function createRun(
  workflowId: string,
  inputs: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<RunDetail> {
  return request<RunDetail>('/runs', {
    method: 'POST',
    body: { workflow_id: workflowId, inputs },
    signal,
  });
}

export function getRun(id: string, signal?: AbortSignal): Promise<RunDetail> {
  return request<RunDetail>(`/runs/${encodeURIComponent(id)}`, { signal });
}

export function getEventsAfter(
  runId: string,
  after = 0,
  signal?: AbortSignal,
): Promise<RunEvent[]> {
  return request<RunEvent[]>(
    `/runs/${encodeURIComponent(runId)}/events?after=${encodeURIComponent(String(after))}`,
    { signal },
  );
}

/**
 * Suscripción SSE. EventSource no permite headers, así que el token viaja en la
 * query string. En cada reconexión se usa el último `seq` recibido como `after`
 * (el contrato admite replay de eventos perdidos). Devuelve una función cleanup.
 */
export function subscribeRunEvents(
  runId: string,
  after: number,
  onEvent: (event: RunEvent) => void,
  onError?: (error: Event) => void,
): () => void {
  let currentAfter = Math.max(0, after);
  let source: EventSource | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const connect = (): void => {
    if (closed) return;
    const token = getToken() ?? '';
    const url =
      `${API_BASE}/runs/${encodeURIComponent(runId)}/stream` +
      `?after=${encodeURIComponent(String(currentAfter))}&token=${encodeURIComponent(token)}`;
    try {
      source = new EventSource(url);
    } catch (error) {
      onError?.(error as Event);
      return;
    }

    source.onmessage = (message: MessageEvent<string>) => {
      if (!message.data) return;
      try {
        const event = JSON.parse(message.data) as RunEvent;
        if (typeof event.seq === 'number') {
          currentAfter = Math.max(currentAfter, event.seq + 1);
        }
        onEvent(event);
      } catch {
        // Un heartbeat o un evento malformado no debe romper el stream.
      }
    };

    source.onerror = (error: Event) => {
      source?.close();
      onError?.(error);
      if (!closed) {
        const token = getToken();
        if (!token) signalUnauthorized();
        retry = setTimeout(connect, 1500);
      }
    };
  };

  connect();

  return () => {
    closed = true;
    if (retry !== null) clearTimeout(retry);
    source?.close();
    source = null;
  };
}

export function cancelRun(id: string, signal?: AbortSignal): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/runs/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
    signal,
  });
}

export function resumeRun(id: string, signal?: AbortSignal): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/runs/${encodeURIComponent(id)}/resume`, {
    method: 'POST',
    signal,
  });
}

export function approveRun(
  id: string,
  decision: ApprovalDecision,
  data?: unknown,
  note?: string,
  signal?: AbortSignal,
): Promise<{ ok: boolean }> {
  const body: Record<string, unknown> = { decision };
  if (data !== undefined) body.data = data;
  if (note !== undefined && note !== '') body.note = note;
  return request<{ ok: boolean }>(`/runs/${encodeURIComponent(id)}/approve`, {
    method: 'POST',
    body,
    signal,
  });
}

/** Descarga de artefactos: el contrato exige el token por header. */
export async function getArtifact(
  runId: string,
  name: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await fetch(
    `${API_BASE}/artifacts/${encodeURIComponent(runId)}/${encodeURIComponent(name)}`,
    { headers: authHeaders(), signal },
  );
  if (response.status === 401) {
    signalUnauthorized();
    throw new TokenRequiredError();
  }
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  return response.blob();
}

export function getArtifactUrl(runId: string, name: string, token = getToken() ?? ''): string {
  return (
    `${API_BASE}/artifacts/${encodeURIComponent(runId)}/${encodeURIComponent(name)}` +
    `?token=${encodeURIComponent(token)}`
  );
}

/** Consume el token que `penfold start` abre en la URL (?token=...). */
export function consumeTokenFromUrl(): string | null {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('token');
    if (!fromUrl) return getToken();
    setToken(fromUrl);
    window.history.replaceState({}, '', window.location.pathname);
    return getToken();
  } catch {
    return getToken();
  }
}

/** Comprobación de arranque: token válido y API accesible. */
export async function checkToken(tokenInfo: TokenInfo): Promise<boolean> {
  const previous = getToken();
  setToken(tokenInfo.token);
  try {
    await getConfig();
    return true;
  } catch (error) {
    if (error instanceof TokenRequiredError || (error instanceof ApiError && error.status === 401)) {
      clearToken();
      return false;
    }
    if (previous) setToken(previous);
    else clearToken();
    throw error;
  }
}
