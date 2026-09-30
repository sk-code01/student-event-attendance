import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AnalyticsFilters } from '../../core/models/analytics.model';
import { ReportDataset, ReportFormat, ReportType } from '../../core/models/report.model';
import { AuthService } from '../../core/services/auth.service';
import { ReportService } from '../../core/services/report.service';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

/**
 * Report generation.
 *
 * The report types offered come from the backend, which returns only those the
 * caller may run — the UI never constructs a report type of its own. That
 * listing is convenience: the export endpoint re-checks the type, the format
 * and the filters against the caller's role on every request, so hiding a
 * type here is not what makes it inaccessible.
 *
 * Downloads go through HttpClient as a blob so the auth interceptor can attach
 * the bearer token; reports live behind an authenticated endpoint and are
 * never exposed at a public URL.
 */
@Component({
  selector: 'app-reports-page',
  standalone: true,
  imports: [FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './reports-page.component.html',
})
export class ReportsPageComponent implements OnInit {
  private readonly reportService = inject(ReportService);
  protected readonly authService = inject(AuthService);

  readonly types = signal<ReportType[]>([]);
  readonly preview = signal<ReportDataset | null>(null);
  readonly loadingTypes = signal(true);
  readonly previewing = signal(false);
  readonly downloading = signal<ReportFormat | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  selectedType = '';
  format: ReportFormat = 'csv';
  dateFrom = '';
  dateTo = '';
  category = '';

  ngOnInit(): void {
    this.reportService.types().subscribe({
      next: (types) => {
        this.types.set(types);
        this.selectedType = types[0]?.key ?? '';
        this.loadingTypes.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load the available report types.');
        this.loadingTypes.set(false);
      },
    });
  }

  private filters(): AnalyticsFilters {
    return {
      date_from: this.dateFrom || undefined,
      date_to: this.dateTo || undefined,
      category: this.category.trim() || undefined,
    };
  }

  /** Guards the obvious client-side mistake; the backend validates regardless. */
  get canGenerate(): boolean {
    return Boolean(this.selectedType) && this.downloading() === null;
  }

  loadPreview(): void {
    if (!this.selectedType) {
      this.errorMessage.set('Choose a report type first.');
      return;
    }
    this.previewing.set(true);
    this.errorMessage.set(null);
    this.successMessage.set(null);
    this.preview.set(null);

    this.reportService.preview(this.selectedType, this.filters()).subscribe({
      next: (dataset) => {
        this.preview.set(dataset);
        this.previewing.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.previewing.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  download(): void {
    if (!this.canGenerate) {
      this.errorMessage.set('Choose a report type first.');
      return;
    }
    this.downloading.set(this.format);
    this.errorMessage.set(null);
    this.successMessage.set(null);

    this.reportService.export(this.selectedType, this.format, this.filters()).subscribe({
      next: (response) => {
        this.downloading.set(null);
        const blob = response.body;
        if (!blob) {
          this.errorMessage.set('The server returned an empty report.');
          return;
        }
        const filename = this.reportService.filenameFrom(
          response.headers.get('Content-Disposition'), this.selectedType, this.format,
        );
        this.saveBlob(blob, filename);
        this.successMessage.set(`Downloaded ${filename}`);
      },
      error: (error: HttpErrorResponse) => {
        this.downloading.set(null);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  /** Object-URL download. Revoked immediately so the blob is not retained. */
  private saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  private messageFor(error: HttpErrorResponse): string {
    if (error.status === 403) {
      return 'That report is not available for your role.';
    }
    if (error.status === 404) {
      return 'That report type, event or department is not available to you.';
    }
    if (error.status === 400) {
      const body = error.error;
      if (body && typeof body === 'object' && !(body instanceof Blob)) {
        const first = Object.values(body)[0];
        return Array.isArray(first) ? String(first[0]) : String(first);
      }
      return 'Those filters are not valid.';
    }
    return 'Unable to generate that report.';
  }

  descriptionFor(key: string): string {
    return this.types().find((t) => t.key === key)?.description ?? '';
  }
}
