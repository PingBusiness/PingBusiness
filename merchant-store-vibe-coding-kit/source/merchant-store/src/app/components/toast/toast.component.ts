import { Component } from '@angular/core';

import { Toast, ToastService } from '../../services/toast.service';

const TITLES: Record<string, string> = {
  success: 'Success',
  error: 'Error',
  warning: 'Warning',
  processing: 'Processing',
  info: 'Notice'
};

@Component({
  selector: 'app-toast',
  templateUrl: './toast.component.html',
  styleUrls: ['./toast.component.css']
})
export class ToastComponent {
  toasts$ = this.toast.toasts$;

  constructor(private toast: ToastService) {}

  titleFor(t: Toast): string {
    return t.title || TITLES[t.type] || 'Notice';
  }

  dismiss(id: number): void {
    this.toast.dismiss(id);
  }
}
