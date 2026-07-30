import { Provider } from "../lib/api";

const FRESHNESS_LABEL: Record<string, string> = {
  fresh: "Fresh",
  due: "Due",
  checking: "Checking",
  blocked: "Blocked",
  stale: "Stale",
  disabled: "Disabled",
};

export function FreshnessDot({ state }: { state: string }) {
  return (
    <span className={`freshness-dot freshness-${state}`} title={FRESHNESS_LABEL[state] ?? state} aria-hidden="true" />
  );
}

export function ProviderSidebar({
  providers,
  selectedId,
  onSelect,
}: {
  providers: Provider[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <nav className="provider-sidebar" aria-label="Providers">
      <h2 className="sidebar-title">Providers</h2>
      <ul className="provider-list">
        {providers.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              className={`provider-item ${p.id === selectedId ? "provider-item-active" : ""}`}
              onClick={() => onSelect(p.id)}
            >
              <FreshnessDot state={p.worst_freshness_state} />
              <span className="provider-name">{p.display_name}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
