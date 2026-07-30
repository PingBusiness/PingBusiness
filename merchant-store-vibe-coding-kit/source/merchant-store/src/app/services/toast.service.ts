import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export type ToastType = 'success' | 'error' | 'info' | 'warning' | 'processing';

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
  title?: string;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private counter = 0;
  private readonly toastsSubject = new BehaviorSubject<Toast[]>([]);
  readonly toasts$ = this.toastsSubject.asObservable();

  show(message: string, type: ToastType = 'success', title?: string, duration = 3200): void {
    if (!message) {
      return;
    }
    const id = ++this.counter;
    this.toastsSubject.next([...this.toastsSubject.value, { id, message, type, title }]);
    if (duration > 0) {
      setTimeout(() => this.dismiss(id), duration);
    }
  }

  dismiss(id: number): void {
    this.toastsSubject.next(this.toastsSubject.value.filter(toast => toast.id !== id));
  }
}
