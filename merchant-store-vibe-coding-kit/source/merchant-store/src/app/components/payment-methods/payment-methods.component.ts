import { Component, EventEmitter, Input, Output } from '@angular/core';

import { paymentNetworkLabel } from '../../utils';

/**
 * "Select payment method" block from the Figma cart / checkout designs.
 *
 * Renders one card per merchant-enabled network. When `selectable` is false the
 * cards are informational only (the hosted subscription selector makes the real
 * choice), which is why the radio is hidden in that mode.
 */
@Component({
  selector: 'app-payment-methods',
  templateUrl: './payment-methods.component.html',
  styleUrls: ['./payment-methods.component.css']
})
export class PaymentMethodsComponent {
  @Input() title = 'Select payment method';
  @Input() description = '';
  @Input() networks: string[] = [];
  @Input() disabled: string[] = [];
  @Input() disabledReason = '';
  @Input() selected = '';
  @Input() selectable = true;
  @Input() loading = false;
  @Output() selectedChange = new EventEmitter<string>();

  /** Card labels follow the design ("Crypto"); the long form stays for order history. */
  label(network: string): string {
    return network === 'Crypto' ? 'Crypto' : paymentNetworkLabel(network);
  }

  isDisabled(network: string): boolean {
    return this.disabled.includes(network);
  }

  choose(network: string): void {
    if (!this.selectable || this.isDisabled(network) || network === this.selected) {
      return;
    }
    this.selected = network;
    this.selectedChange.emit(network);
  }
}
