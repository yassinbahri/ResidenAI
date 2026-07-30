import { useEffect, useState } from "react";
import { ApiError, Product, Provider, Source, getProviderProducts, getProviderSources, getProviders } from "./lib/api";
import { ProviderSidebar } from "./components/ProviderSidebar";
import { ResidencyStatusCard } from "./components/ResidencyStatusCard";
import { SourceTable } from "./components/SourceTable";
import { TokenGate } from "./components/TokenGate";
import { useAdminToken } from "./hooks/useAdminToken";

export default function App() {
  const [adminToken, setAdminToken] = useAdminToken();
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!adminToken) return;
    getProviders(adminToken)
      .then((p) => {
        setProviders(p);
        setError(null);
        if (p.length > 0 && !selectedProviderId) setSelectedProviderId(p[0].id);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          setAdminToken("");
          return;
        }
        setError(err instanceof ApiError ? err.message : "Could not load providers.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adminToken]);

  useEffect(() => {
    if (!adminToken || !selectedProviderId) return;
    setSources(null);
    setProducts(null);
    getProviderSources(adminToken, selectedProviderId)
      .then(setSources)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load sources."));
    getProviderProducts(adminToken, selectedProviderId)
      .then(setProducts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load residency status."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adminToken, selectedProviderId]);

  if (!adminToken) {
    return <TokenGate onConnected={setAdminToken} />;
  }

  const selectedProvider = providers?.find((p) => p.id === selectedProviderId) ?? null;

  return (
    <div className="page">
      <header className="top-bar">
        <div className="wordmark">
          <span className="wordmark-mark" aria-hidden="true">
            ◆
          </span>
          <div>
            <h1>Residency Tracker</h1>
            <p className="subtitle">Internal only - AI vendor data-residency and compliance evidence.</p>
          </div>
        </div>
        <button type="button" className="button-ghost" onClick={() => setAdminToken("")}>
          Disconnect
        </button>
      </header>

      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}

      <main className="tracker-layout">
        {providers ? (
          <ProviderSidebar providers={providers} selectedId={selectedProviderId} onSelect={setSelectedProviderId} />
        ) : (
          <p className="empty-state">Loading providers…</p>
        )}

        <section className="tracker-main">
          {selectedProvider && (
            <div className="provider-header">
              <h2>{selectedProvider.display_name}</h2>
              {selectedProvider.website_url && (
                <a href={selectedProvider.website_url} target="_blank" rel="noreferrer">
                  {selectedProvider.website_url}
                </a>
              )}
            </div>
          )}
          {products && products.length > 0 && selectedProvider && (
            <div className="residency-cards">
              {products.map((product) => (
                <ResidencyStatusCard key={product.id} provider={selectedProvider} product={product} />
              ))}
            </div>
          )}
          {sources ? (
            <SourceTable adminToken={adminToken} sources={sources} />
          ) : (
            <p className="empty-state">Loading sources…</p>
          )}
        </section>
      </main>
    </div>
  );
}
