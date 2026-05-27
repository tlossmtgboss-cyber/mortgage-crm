// CIE — API fetch wrappers

import { getToken } from "../utils/tokenStore";
import type { CIEReport, CIEStats, ReportListResponse } from "./cie-types";

function getApiBase(): string {
  const isLocalhost =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";
  const origin = isLocalhost
    ? process.env.REACT_APP_API_URL || "http://localhost:8000"
    : "https://api.perenniaai.com";
  return origin + "/api/v1/cie";
}

async function cieRequest<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`${getApiBase()}${path}`, {
    headers: {
      Authorization: token ? `Bearer ${token}` : "",
      "Content-Type": "application/json",
    },
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`CIE API ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

export function fetchReport(reportId: string): Promise<CIEReport> {
  return cieRequest<CIEReport>(`/reports/${reportId}`);
}

export function fetchReportsForLoan(
  loanId: number,
  limit = 20,
  offset = 0,
): Promise<ReportListResponse> {
  return cieRequest<ReportListResponse>(
    `/reports?loan_id=${loanId}&limit=${limit}&offset=${offset}`,
  );
}

export function fetchReportsForLead(
  leadId: number,
  limit = 20,
  offset = 0,
): Promise<ReportListResponse> {
  return cieRequest<ReportListResponse>(
    `/reports?lead_id=${leadId}&limit=${limit}&offset=${offset}`,
  );
}

export function fetchTranscript(
  reportId: string,
): Promise<{ transcript: string }> {
  return cieRequest<{ transcript: string }>(`/reports/${reportId}/transcript`);
}

export function fetchRecordingUrl(
  reportId: string,
): Promise<{ recording_url: string }> {
  return cieRequest<{ recording_url: string }>(
    `/reports/${reportId}/recording`,
  );
}

export function fetchStats(loanId?: number): Promise<CIEStats> {
  const params = loanId ? `?loan_id=${loanId}` : "";
  return cieRequest<CIEStats>(`/stats${params}`);
}
