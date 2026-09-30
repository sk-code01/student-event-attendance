import { Component, input } from '@angular/core';

/**
 * The one sentence every AI view must carry. The text comes from the backend
 * response when available so the wording is defined in exactly one place;
 * the fallback is the same sentence for the states where no response exists
 * yet (loading, network error).
 */
@Component({
  selector: 'app-ai-disclaimer',
  standalone: true,
  template: `
    <div class="alert alert-secondary py-2 small mb-3" role="note">
      <strong>Decision support only.</strong>
      {{ text() || FALLBACK }}
    </div>
  `,
})
export class AiDisclaimerComponent {
  readonly text = input<string | null | undefined>(null);
  protected readonly FALLBACK =
    'AI-generated decision-support signal. Final academic decisions remain with authorized Faculty/Event Coordinator personnel.';
}
