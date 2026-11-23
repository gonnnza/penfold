import { afterEach, vi } from 'vitest';

// Node 26 expone un `localStorage` global experimental que, bajo jsdom en
// Vitest, deja `window.localStorage` a undefined. Instalamos un Storage en
// memoria para que el cliente HTTP pueda leer/escribir el token en los tests.
const memory = new Map<string, string>();
const memoryStorage: Storage = {
  get length() {
    return memory.size;
  },
  clear: () => memory.clear(),
  getItem: (key) => memory.get(key) ?? null,
  key: (index) => Array.from(memory.keys())[index] ?? null,
  removeItem: (key) => {
    memory.delete(key);
  },
  setItem: (key, value) => {
    memory.set(key, String(value));
  },
};
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  writable: true,
  value: memoryStorage,
});
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  writable: true,
  value: memoryStorage,
});

// jsdom doesn't implement matchMedia; a few UI primitives probe it on mount.
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

afterEach(() => {
  memoryStorage.clear();
  vi.restoreAllMocks();
});
