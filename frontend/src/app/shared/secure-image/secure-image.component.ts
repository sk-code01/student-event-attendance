import { HttpClient } from '@angular/common/http';
import { Component, Input, OnChanges, OnDestroy, signal } from '@angular/core';

/**
 * Renders an image that lives behind an authenticated backend endpoint
 * (evidence/participation capture images are never public URLs — see
 * apps.verification.views.EvidenceCaptureImageView). A plain `<img [src]>`
 * cannot carry the Authorization header the interceptor attaches to
 * HttpClient requests, so this fetches the bytes via HttpClient as a blob
 * and renders them through a local object URL instead.
 */
@Component({
  selector: 'app-secure-image',
  standalone: true,
  template: `
    @if (objectUrl(); as url) {
      <img [src]="url" [alt]="alt" class="img-fluid rounded" />
    } @else if (failed()) {
      <div class="text-muted small border rounded p-3 text-center">Image unavailable</div>
    } @else {
      <div class="text-muted small border rounded p-3 text-center">Loading&hellip;</div>
    }
  `,
})
export class SecureImageComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) src!: string;
  @Input() alt = 'Evidence capture';

  readonly objectUrl = signal<string | null>(null);
  readonly failed = signal(false);

  constructor(private readonly http: HttpClient) {}

  ngOnChanges(): void {
    this.releaseUrl();
    this.failed.set(false);
    if (!this.src) return;

    this.http.get(this.src, { responseType: 'blob' }).subscribe({
      next: (blob) => this.objectUrl.set(URL.createObjectURL(blob)),
      error: () => this.failed.set(true),
    });
  }

  ngOnDestroy(): void {
    this.releaseUrl();
  }

  private releaseUrl(): void {
    const url = this.objectUrl();
    if (url) URL.revokeObjectURL(url);
    this.objectUrl.set(null);
  }
}
