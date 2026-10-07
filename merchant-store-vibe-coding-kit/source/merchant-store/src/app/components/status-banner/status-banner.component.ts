import { Component, Input } from '@angular/core';

/** Full-width toast from the Figma checkout designs (green success, red failure). */
@Component({
  selector: 'app-status-banner',
  templateUrl: './status-banner.component.html',
  styleUrls: ['./status-banner.component.css']
})
export class StatusBannerComponent {
  @Input() type: 'success' | 'error' = 'success';
  @Input() title = '';
  @Input() message = '';
}
