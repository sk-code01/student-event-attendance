import { Injectable, signal } from '@angular/core';

export type ToastKind = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  text?: string;
}

/** Errors stay up longer than confirmations — there is usually something to read. */
const DEFAULT_TTL: Record<ToastKind, number> = {
  success: 4000,
  info: 5000,
  warning: 7000,
  error: 9000,
};

/**
 * Transient feedback.
 *
 * Toasts are for *immediate* feedback on an action the user just took. They
 * are not a substitute for the Notification Centre, which holds persistent,
 * server-generated notifications — the two are deliberately separate, and a
 * toast never pretends to be a notification.
 *
 * Form validation stays inline, not here: an error about a field belongs
 * beside that field.
 */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private nextId = 1;
  private readonly timers = new Map<number, ReturnType<typeof setTimeout>>();

  private readonly _toasts = signal<Toast[]>([]);
  readonly toasts = this._toasts.asReadonly();

  success(title: string, text?: string): number { return this.show('success', title, text); }
  error(title: string, text?: string): number { return this.show('error', title, text); }
  warning(title: string, text?: string): number { return this.show('warning', title, text); }
  info(title: string, text?: string): number { return this.show('info', title, text); }

  show(kind: ToastKind, title: string, text?: string, ttl = DEFAULT_TTL[kind]): number {
    const id = this.nextId++;
    this._toasts.update((list) => [...list, { id, kind, title, text }]);
    this.timers.set(id, setTimeout(() => this.dismiss(id), ttl));
    return id;
  }

  dismiss(id: number): void {
    const timer = this.timers.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      this.timers.delete(id);
    }
    this._toasts.update((list) => list.filter((toast) => toast.id !== id));
  }

  clear(): void {
    this.timers.forEach((timer) => clearTimeout(timer));
    this.timers.clear();
    this._toasts.set([]);
  }
}
