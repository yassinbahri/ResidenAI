const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8100";

export interface Provider {
  id: string;
  slug: string;
  display_name: string;
  website_url: string | null;
  source_count: number;
  enabled_source_count: number;
  worst_freshness_state: string;
  eu_domicile_status: "eu_domiciled" | "non_eu_domiciled" | "unclear" | "conflicting";
  eu_domicile_evidence_quote: string | null;
  eu_domicile_evidence_source_key: string | null;
  eu_domicile_evidence_char_start: number | null;
  eu_domicile_evidence_char_end: number | null;
  eu_domicile_evaluated_at: string | null;
  eu_domicile_conflicting_quote: string | null;
  eu_domicile_conflicting_source_key: string | null;
  registry_verified_country: string | null;
  registry_source: string | null;
  registry_checked_at: string | null;
}

export interface Product {
  id: string;
  slug: string;
  display_name: string;
  product_type: string;
  eu_eea_status: "available" | "selectable" | "not_available" | "unclear";
  eu_eea_evidence_quote: string | null;
  eu_eea_evidence_source_key: string | null;
  eu_eea_evidence_char_start: number | null;
  eu_eea_evidence_char_end: number | null;
  eu_eea_evaluated_at: string | null;
  eu_alignment_score: number;
  eu_alignment_tier: string;
}

export interface Source {
  id: string;
  source_key: string;
  canonical_url: string;
  authority: string;
  source_class: string;
  enabled: boolean;
  product_display_name: string;
  freshness_state: string;
  last_success_at: string | null;
  last_change_at: string | null;
  failure_count: number;
}

export interface VersionSummary {
  id: string;
  created_at: string;
  title: string | null;
  predecessor_id: string | null;
}

export interface VersionDetail extends VersionSummary {
  source_id: string;
  normalized_content: string;
}

export interface DiffResponse {
  version_id: string;
  predecessor_id: string | null;
  is_first_version: boolean;
  diff_lines: string[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code: string | null = null,
  ) {
    super(message);
  }
}

function extractDetail(body: string): { message: string; code: string | null } {
  try {
    const parsed = JSON.parse(body);
    const detail = parsed.detail ?? parsed;
    return { message: detail.message ?? body, code: detail.error_code ?? null };
  } catch {
    return { message: body, code: null };
  }
}

async function request<T>(path: string, adminToken: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "X-Admin-Token": adminToken,
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    const { message, code } = extractDetail(body);
    throw new ApiError(response.status, message || response.statusText, code);
  }
  return (await response.json()) as T;
}

export function getProviders(adminToken: string): Promise<Provider[]> {
  return request<Provider[]>("/providers", adminToken);
}

export function getProviderSources(adminToken: string, providerId: string): Promise<Source[]> {
  return request<Source[]>(`/providers/${providerId}/sources`, adminToken);
}

export function getProviderProducts(adminToken: string, providerId: string): Promise<Product[]> {
  return request<Product[]>(`/providers/${providerId}/products`, adminToken);
}

export function getSourceVersions(adminToken: string, sourceId: string): Promise<VersionSummary[]> {
  return request<VersionSummary[]>(`/sources/${sourceId}/versions`, adminToken);
}

export function getVersion(adminToken: string, versionId: string): Promise<VersionDetail> {
  return request<VersionDetail>(`/versions/${versionId}`, adminToken);
}

export function getVersionDiff(adminToken: string, versionId: string): Promise<DiffResponse> {
  return request<DiffResponse>(`/versions/${versionId}/diff`, adminToken);
}
