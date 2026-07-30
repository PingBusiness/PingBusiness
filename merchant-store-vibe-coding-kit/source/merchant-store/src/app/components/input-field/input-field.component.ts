import { Component, EventEmitter, Input, Output, forwardRef } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

let uid = 0;

@Component({
  selector: 'app-input-field',
  templateUrl: './input-field.component.html',
  styleUrls: ['./input-field.component.css'],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => InputFieldComponent),
      multi: true
    }
  ]
})
export class InputFieldComponent implements ControlValueAccessor {
  @Input() type = 'text';
  @Input() icon: 'envelope' | 'lock' | 'user' | 'contact' | 'home' | '' = '';
  @Input() placeholder = '';
  @Input() autocomplete = '';
  @Input() inputName = '';
  @Input() error = '';
  @Input() linkText = '';
  @Input() disabled = false;
  @Output() linkClick = new EventEmitter<void>();

  readonly inputId = `input-field-${++uid}`;
  value = '';
  revealed = false;

  get isPassword(): boolean {
    return this.type === 'password';
  }

  get inputType(): string {
    return this.isPassword ? (this.revealed ? 'text' : 'password') : this.type;
  }

  toggleReveal(): void {
    this.revealed = !this.revealed;
  }

  private onChange: (value: string) => void = () => undefined;
  private onTouched: () => void = () => undefined;

  writeValue(value: string): void {
    this.value = value ?? '';
  }

  registerOnChange(fn: (value: string) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled = isDisabled;
  }

  onInput(value: string): void {
    this.value = value;
    this.onChange(value);
  }

  onBlur(): void {
    this.onTouched();
  }
}
