import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  TOKEN_KEY,
  approveRun,
  consumeTokenFromUrl,
  createRun,
  getConfig,
  getEventsAfter,
  listAgents,
  saveWorkflow,
  subscribeRunEvents,
  validateWorkflow,
} from './api';
import type { RunEvent, WorkflowDefinition } from './types';

const workflow: WorkflowDefinition = {
  schema_version: 1,
  metadata: { id: 'wf-1', name: 'Demo' },
  inputs: [],
  nodes: [],
  edges: [],
};

function mockFetch(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'Error',
    text: async () => JSON.stringify(body),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

class MockEventSource {
  static instances: MockEventSource[] = [];
  readonly url: string;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }
}

const sampleEvent: RunEvent = {
  id: 1,
  run_id: 'run-1',
  seq: 7,
  type: 'node_succeeded',
  level: 'success',
  node_id: 'node-1',
  message: 'ok',
  data: null,
  timestamp: '2026-01-01T00:00:00Z',
};

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(TOKEN_KEY, 'secret-token');
    MockEventSource.instances = [];
    vi.stubGlobal('EventSource', MockEventSource);
  });

  it('consume el token de la URL inicial y limpia la query', () => {
    window.history.replaceState({}, '', '/?token=from-url');
    expect(consumeTokenFromUrl()).toBe('from-url');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('from-url');
    expect(window.location.search).toBe('');
  });

  it('envía X-Penfold-Token en GET y usa la ruta /api/config', async () => {
    const fetchMock = mockFetch({ project: { name: 'Penfold', description: '' } });
    await getConfig();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/config');
    expect(init.method).toBe('GET');
    expect((init.headers as Record<string, string>)['X-Penfold-Token']).toBe('secret-token');
    expect(init.body).toBeUndefined();
  });

  it('guarda y valida workflows con el método y body correctos', async () => {
    const saveMock = mockFetch({ ok: true, id: 'wf-1', issues: [] });
    await saveWorkflow(workflow);

    const [saveUrl, saveInit] = saveMock.mock.calls[0] as [string, RequestInit];
    expect(saveUrl).toBe('/api/workflows/wf-1');
    expect(saveInit.method).toBe('PUT');
    expect((saveInit.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(JSON.parse(String(saveInit.body))).toEqual(workflow);

    const validateMock = mockFetch({ valid: true, issues: [] });
    await validateWorkflow(workflow);
    const [validateUrl, validateInit] = validateMock.mock.calls[0] as [string, RequestInit];
    expect(validateUrl).toBe('/api/workflows/validate');
    expect(validateInit.method).toBe('POST');
  });

  it('crea runs, consulta eventos y envía decisiones de aprobación', async () => {
    const runMock = mockFetch({ id: 'run-1' }, 201);
    await createRun('wf-1', { tema: 'x' });
    expect(runMock.mock.calls[0][0]).toBe('/api/runs');
    expect(JSON.parse(String((runMock.mock.calls[0][1] as RequestInit).body))).toEqual({
      workflow_id: 'wf-1',
      inputs: { tema: 'x' },
    });

    const eventsMock = mockFetch([sampleEvent]);
    const events = await getEventsAfter('run-1', 7);
    expect(events).toHaveLength(1);
    expect(eventsMock.mock.calls[0][0]).toBe('/api/runs/run-1/events?after=7');

    const approveMock = mockFetch({ ok: true });
    await approveRun('run-1', 'modify', { resultado: 42 }, 'nota');
    expect(approveMock.mock.calls[0][0]).toBe('/api/runs/run-1/approve');
    expect(JSON.parse(String((approveMock.mock.calls[0][1] as RequestInit).body))).toEqual({
      decision: 'modify',
      data: { resultado: 42 },
      note: 'nota',
    });
  });

  it('lista agentes con el token configurado', async () => {
    const fetchMock = mockFetch([]);
    await listAgents();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/agents');
  });

  it('borra el token y lanza TokenRequiredError ante un 401', async () => {
    mockFetch({ detail: 'invalid token' }, 401);
    const unauthorized = vi.fn();
    window.addEventListener('penfold:unauthorized', unauthorized);

    await expect(getConfig()).rejects.toMatchObject({ name: 'TokenRequiredError' });
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(unauthorized).toHaveBeenCalledTimes(1);
    window.removeEventListener('penfold:unauthorized', unauthorized);
  });

  it('muestra detalles de error HTTP', async () => {
    mockFetch({ detail: 'workflow inválido' }, 422);
    await expect(validateWorkflow(workflow)).rejects.toBeInstanceOf(ApiError);
    await expect(validateWorkflow(workflow)).rejects.toMatchObject({
      status: 422,
      detail: 'workflow inválido',
    });
  });

  it('abre el SSE con token en la query y reenvía los eventos', () => {
    const onEvent = vi.fn();
    const unsubscribe = subscribeRunEvents('run-1', 5, onEvent);
    const source = MockEventSource.instances[0];

    expect(source.url).toBe('/api/runs/run-1/stream?after=5&token=secret-token');
    source.onmessage?.({ data: JSON.stringify(sampleEvent) } as MessageEvent<string>);
    expect(onEvent).toHaveBeenCalledWith(sampleEvent);

    unsubscribe();
    expect(source.closed).toBe(true);
  });
});
