import type { NodeType } from './types';

export interface NodeMeta {
  label: string;
  description: string;
  category: string;
  defaultConfig: () => Record<string, unknown>;
}

export const NODE_CATEGORIES = [
  { id: 'input', label: 'Input', types: ['input'] },
  { id: 'agents', label: 'Agents', types: ['agent'] },
  { id: 'tools', label: 'Tools', types: ['command'] },
  { id: 'logic', label: 'Logic', types: ['condition'] },
  { id: 'human', label: 'Human', types: ['approval'] },
  { id: 'output', label: 'Output', types: ['output'] },
] as const satisfies ReadonlyArray<{ id: string; label: string; types: readonly NodeType[] }>;

export const NODE_META: Record<NodeType, NodeMeta> = {
  input: {
    label: 'Input',
    description: 'Punto de entrada del workflow',
    category: 'Input',
    defaultConfig: () => ({}),
  },
  agent: {
    label: 'Agent',
    description: 'Ejecuta un agente definido en /agents',
    category: 'Agents',
    defaultConfig: () => ({ inputs: {}, timeout: 30, retries: 0, context: [] }),
  },
  command: {
    label: 'Command',
    description: 'Comando local (sin shell)',
    category: 'Tools',
    defaultConfig: () => ({ command: '', cwd: '.', timeout: 30, inputs: {} }),
  },
  condition: {
    label: 'Condition',
    description: 'Bifurca por pass / fail',
    category: 'Logic',
    defaultConfig: () => ({
      expression: { field: '', op: 'eq', value: '' },
      inputs: {},
    }),
  },
  approval: {
    label: 'Approval',
    description: 'Pausa para decisión humana',
    category: 'Human',
    defaultConfig: () => ({ title: '', message: '', inputs: {} }),
  },
  output: {
    label: 'Output',
    description: 'Resultado final del workflow',
    category: 'Output',
    defaultConfig: () => ({ inputs: {}, format: 'json' }),
  },
};

export const CONDITION_OPS = [
  'eq',
  'ne',
  'gt',
  'gte',
  'lt',
  'lte',
  'contains',
  'in',
  'exists',
] as const;

export function isNodeType(value: string): value is NodeType {
  return value in NODE_META;
}
