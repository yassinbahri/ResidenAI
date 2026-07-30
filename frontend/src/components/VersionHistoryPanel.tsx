import { useEffect, useState } from "react";
import {
  ApiError,
  DiffResponse,
  Source,
  VersionDetail,
  VersionSummary,
  getSourceVersions,
  getVersion,
  getVersionDiff,
} from "../lib/api";
import { DiffView } from "./DiffView";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function VersionHistoryPanel({ adminToken, source }: { adminToken: string; source: Source }) {
  const [versions, setVersions] = useState<VersionSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<VersionDetail | null>(null);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setVersions(null);
    setSelectedId(null);
    setDetail(null);
    setDiff(null);
    getSourceVersions(adminToken, source.id)
      .then((v) => {
        setVersions(v);
        if (v.length > 0) setSelectedId(v[0].id);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load version history."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source.id]);

  useEffect(() => {
    if (!selectedId) return;
    setDetail(null);
    setDiff(null);
    Promise.all([getVersion(adminToken, selectedId), getVersionDiff(adminToken, selectedId)])
      .then(([d, diffResult]) => {
        setDetail(d);
        setDiff(diffResult);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load version detail."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  if (error) {
    return (
      <p className="error-banner" role="alert">
        {error}
      </p>
    );
  }

  if (versions === null) {
    return <p className="empty-state">Loading version history…</p>;
  }

  if (versions.length === 0) {
    return <p className="empty-state">No versions captured yet for this source.</p>;
  }

  return (
    <div className="version-history-panel">
      <ul className="version-list">
        {versions.map((v) => (
          <li key={v.id}>
            <button
              type="button"
              className={`version-item ${v.id === selectedId ? "version-item-active" : ""}`}
              onClick={() => setSelectedId(v.id)}
            >
              <span className="version-date">{formatDate(v.created_at)}</span>
            </button>
          </li>
        ))}
      </ul>

      <div className="version-detail">
        {detail && diff ? (
          <>
            <h3 className="version-detail-title">{detail.title ?? "(untitled)"}</h3>
            <DiffView diff={diff} />
          </>
        ) : (
          <p className="empty-state">Loading…</p>
        )}
      </div>
    </div>
  );
}
