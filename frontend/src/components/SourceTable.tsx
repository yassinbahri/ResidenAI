import { useState } from "react";
import { Source } from "../lib/api";
import { FreshnessDot } from "./ProviderSidebar";
import { VersionHistoryPanel } from "./VersionHistoryPanel";

function formatDate(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString();
}

function SourceRow({ adminToken, source }: { adminToken: string; source: Source }) {
  const [expanded, setExpanded] = useState(false);
  const detailId = `source-detail-${source.id}`;

  return (
    <>
      <tr className={expanded ? "row-expanded" : undefined}>
        <td>
          <button
            type="button"
            className="row-expand-toggle"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-controls={detailId}
          >
            <span className={`row-expand-chevron ${expanded ? "row-expand-chevron-open" : ""}`} aria-hidden="true">
              ▸
            </span>
            <FreshnessDot state={source.freshness_state} />
            {source.source_key}
          </button>
          {!source.enabled && <span className="status-badge status-neutral disabled-badge">Disabled</span>}
        </td>
        <td>{source.product_display_name}</td>
        <td>
          <a href={source.canonical_url} target="_blank" rel="noreferrer" className="source-url">
            {source.canonical_url}
          </a>
        </td>
        <td className="mono">{source.authority}</td>
        <td className="numeric-cell">{formatDate(source.last_success_at)}</td>
      </tr>
      {expanded && (
        <tr className="expanded-row" id={detailId}>
          <td colSpan={5}>
            <VersionHistoryPanel adminToken={adminToken} source={source} />
          </td>
        </tr>
      )}
    </>
  );
}

export function SourceTable({ adminToken, sources }: { adminToken: string; sources: Source[] }) {
  if (sources.length === 0) {
    return <p className="empty-state">No sources registered for this provider.</p>;
  }

  return (
    <div className="table-scroll">
      <table className="source-table">
        <caption className="visually-hidden">Sources for the selected provider</caption>
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Product</th>
            <th scope="col">URL</th>
            <th scope="col">Authority</th>
            <th scope="col">Last checked</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <SourceRow key={s.id} adminToken={adminToken} source={s} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
