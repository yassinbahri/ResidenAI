import { Product, Provider } from "../lib/api";

const RESIDENCY_LABEL: Record<Product["eu_eea_status"], string> = {
  available: "Available",
  selectable: "Selectable (not default)",
  not_available: "Not available",
  unclear: "Unclear",
};

const DOMICILE_LABEL: Record<Provider["eu_domicile_status"], string> = {
  eu_domiciled: "EU/EEA-domiciled company",
  non_eu_domiciled: "Non-EU/EEA-domiciled company",
  unclear: "Domicile unclear",
  conflicting: "Conflicting domicile evidence",
};

const STATUS_CLASS: Record<string, string> = {
  available: "status-good",
  eu_domiciled: "status-good",
  selectable: "status-warning",
  not_available: "status-critical",
  non_eu_domiciled: "status-critical",
  unclear: "status-neutral",
  conflicting: "status-serious",
};

function scoreClass(score: number, tier: string): string {
  if (tier === "Insufficient data") return "status-neutral";
  if (tier === "Conflicting evidence") return "status-serious";
  if (score >= 80) return "status-good";
  if (score >= 50) return "status-warning";
  if (score >= 25) return "status-serious";
  return "status-critical";
}

function formatDate(iso: string | null): string {
  if (!iso) return "never evaluated";
  return new Date(iso).toLocaleString();
}

export function ResidencyStatusCard({ provider, product }: { provider: Provider; product: Product }) {
  return (
    <div className="residency-card">
      <div className="residency-card-header">
        <span className="residency-product-name">{product.display_name}</span>
        <span className={`eu-score ${scoreClass(product.eu_alignment_score, product.eu_alignment_tier)}`}>
          {product.eu_alignment_score}/100 — {product.eu_alignment_tier}
        </span>
      </div>

      <div className="residency-signals">
        <div className="residency-signal">
          <span className={`status-badge ${STATUS_CLASS[provider.eu_domicile_status]}`}>
            {DOMICILE_LABEL[provider.eu_domicile_status]}
          </span>
          {provider.eu_domicile_evidence_quote ? (
            <p className="residency-evidence">
              “…{provider.eu_domicile_evidence_quote}…”
              {provider.eu_domicile_evidence_source_key && (
                <span className="residency-evidence-source"> — {provider.eu_domicile_evidence_source_key}</span>
              )}
            </p>
          ) : (
            <p className="residency-evidence residency-evidence-empty">
              No self-referential domicile statement found yet.
            </p>
          )}
          {provider.eu_domicile_status === "conflicting" && provider.eu_domicile_conflicting_quote && (
            <p className="residency-evidence residency-evidence-conflict">
              vs. “…{provider.eu_domicile_conflicting_quote}…”
              {provider.eu_domicile_conflicting_source_key && (
                <span className="residency-evidence-source"> — {provider.eu_domicile_conflicting_source_key}</span>
              )}
            </p>
          )}
          {provider.registry_verified_country && (
            <p className="residency-evidence residency-evidence-registry">
              Registry corroboration ({provider.registry_source}): {provider.registry_verified_country}
            </p>
          )}
        </div>

        <div className="residency-signal">
          <span className={`status-badge ${STATUS_CLASS[product.eu_eea_status]}`}>
            Processing: {RESIDENCY_LABEL[product.eu_eea_status]}
          </span>
          {product.eu_eea_evidence_quote ? (
            <p className="residency-evidence">
              “…{product.eu_eea_evidence_quote}…”
              {product.eu_eea_evidence_source_key && (
                <span className="residency-evidence-source"> — {product.eu_eea_evidence_source_key}</span>
              )}
            </p>
          ) : (
            <p className="residency-evidence residency-evidence-empty">
              No EU/EEA-specific wording found yet in captured content.
            </p>
          )}
        </div>
      </div>

      <p className="residency-caveat">
        Automatic keyword signal, not a legal conclusion — verify before relying on it. Last evaluated:{" "}
        {formatDate(product.eu_eea_evaluated_at)}.
      </p>
    </div>
  );
}
