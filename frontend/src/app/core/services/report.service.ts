import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { AnalyticsFilters } from '../models/analytics.model';
import { ReportDataset, ReportFormat, ReportType } from '../models/report.model';

/**
 * Report API client.
 *
 * Downloads go through `HttpClient` with `responseType: 'blob'` so the
 * existing auth interceptor attaches the bearer token — reports are personal
 * academic data behind an authenticated endpoint, and a plain anchor href
 * could not carry the header. The same pattern `SecureImageComponent` uses for
 * evidence images.
 *
 * Report type and format are whatever the backend offered; it re-validates
 * both against its own allowlist on every request.
 */
@Injectable({ providedIn: 'root' })
export class ReportService {
  private readonly baseUrl = `${environment.apiBaseUrl}/reports`;

  constructor(private readonly http: HttpClient) {}

  private params(filters: AnalyticsFilters = {}): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        params = params.set(key, String(value));
      }
    }
    return params;
  }

  /** The report types this caller may run. */
  types(): Observable<ReportType[]> {
    return this.http.get<ReportType[]>(`${this.baseUrl}/`);
  }

  /** A JSON view of the exact rows the export will contain. */
  preview(reportType: string, filters: AnalyticsFilters = {}): Observable<ReportDataset> {
    return this.http.get<ReportDataset>(
      `${this.baseUrl}/${reportType}/`, { params: this.params(filters) },
    );
  }

  /**
   * Downloads the generated file. Returns the full response so the caller can
   * read `Content-Disposition` for the server-chosen filename rather than
   * inventing one.
   */
  export(reportType: string, format: ReportFormat, filters: AnalyticsFilters = {}) {
    return this.http.get(`${this.baseUrl}/${reportType}/export/`, {
      // `file_format`, not `format`: DRF reserves the `format` query parameter
      // for renderer content negotiation, and an unknown value there makes the
      // server return 404 before it ever reaches the view.
      params: this.params(
        { ...filters, file_format: format } as AnalyticsFilters & { file_format: ReportFormat },
      ),
      responseType: 'blob',
      observe: 'response',
    });
  }

  /**
   * Extracts the filename the server set. Falls back to a safe generated name
   * if the header is absent, and never trusts it to contain a path — only the
   * final segment is used.
   */
  filenameFrom(disposition: string | null, reportType: string, format: ReportFormat): string {
    const match = disposition?.match(/filename="?([^";]+)"?/i);
    const raw = match?.[1]?.trim();
    if (!raw) {
      return `${reportType}.${format}`;
    }
    const lastSegment = raw.split(/[\\/]/).pop() ?? '';
    return lastSegment || `${reportType}.${format}`;
  }
}
