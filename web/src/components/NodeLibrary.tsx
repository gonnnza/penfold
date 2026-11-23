import type { DragEvent } from 'react';
import { Bot, GitBranch, GripVertical, Hand, LogIn, LogOut, Terminal, type LucideIcon } from 'lucide-react';
import { NODE_CATEGORIES, NODE_META } from '../nodeMeta';
import type { NodeType } from '../types';

export const NODE_ICONS: Record<NodeType, LucideIcon> = {
  input: LogIn,
  agent: Bot,
  command: Terminal,
  condition: GitBranch,
  approval: Hand,
  output: LogOut,
};

export const NODE_DRAG_MIME = 'application/penfold-node';

interface NodeLibraryProps {
  onAdd: (type: NodeType) => void;
}

export function NodeLibrary({ onAdd }: NodeLibraryProps) {
  const handleDragStart = (event: DragEvent<HTMLButtonElement>, type: NodeType): void => {
    event.dataTransfer.setData(NODE_DRAG_MIME, type);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <aside className="panel library" aria-label="Librería de nodos">
      <div className="panel-header">
        <h2>Librería</h2>
        <span className="muted tiny">arrastra al canvas</span>
      </div>
      <div className="library-scroll">
        {NODE_CATEGORIES.map((category) => (
          <section className="library-category" key={category.id}>
            <h3>{category.label}</h3>
            {category.types.map((type) => {
              const meta = NODE_META[type];
              const Icon = NODE_ICONS[type];
              return (
                <button
                  key={type}
                  type="button"
                  className="library-item"
                  draggable
                  onDragStart={(event) => handleDragStart(event, type)}
                  onDoubleClick={() => onAdd(type)}
                  title={`${meta.description} (doble clic para añadir)`}
                  aria-label={`Añadir nodo ${meta.label}`}
                >
                  <span className={`library-icon node-${type}`}>
                    <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
                  </span>
                  <span className="library-text">
                    <strong>{meta.label}</strong>
                    <small>{meta.description}</small>
                  </span>
                  <GripVertical size={13} className="muted" aria-hidden="true" />
                </button>
              );
            })}
          </section>
        ))}
      </div>
      <div className="library-footer muted tiny">
        <kbd>Del</kbd> borrar · <kbd>Ctrl</kbd>+<kbd>Z</kbd> deshacer
      </div>
    </aside>
  );
}
