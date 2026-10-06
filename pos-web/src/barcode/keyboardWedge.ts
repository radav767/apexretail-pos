export type WedgeKey = {
  key: string;
  timestamp: number;
  modifier?: boolean;
  repeat?: boolean;
  composing?: boolean;
};

export type KeyboardWedgeOptions = {
  maxInterKeyMs?: number;
  maxSequenceMs?: number;
  minLength?: number;
};

export class KeyboardWedgeDetector {
  private buffer = "";
  private startedAt = 0;
  private lastAt = 0;
  private readonly maxInterKeyMs: number;
  private readonly maxSequenceMs: number;
  private readonly minLength: number;

  constructor(options: KeyboardWedgeOptions = {}) {
    this.maxInterKeyMs = options.maxInterKeyMs ?? 60;
    this.maxSequenceMs = options.maxSequenceMs ?? 1_000;
    this.minLength = options.minLength ?? 4;
  }

  reset() {
    this.buffer = "";
    this.startedAt = 0;
    this.lastAt = 0;
  }

  feed(input: WedgeKey): string | null {
    if (input.modifier || input.repeat || input.composing) {
      this.reset();
      return null;
    }

    if (input.key === "Enter") {
      const duration = input.timestamp - this.startedAt;
      const value = this.buffer;
      const valid =
        value.length >= this.minLength &&
        this.startedAt > 0 &&
        input.timestamp - this.lastAt <= this.maxInterKeyMs * 2 &&
        duration <= this.maxSequenceMs;
      this.reset();
      return valid ? value : null;
    }

    if (input.key.length !== 1) {
      this.reset();
      return null;
    }

    if (this.lastAt && input.timestamp - this.lastAt > this.maxInterKeyMs) {
      this.reset();
    }
    if (!this.startedAt) this.startedAt = input.timestamp;
    this.lastAt = input.timestamp;
    this.buffer += input.key;
    return null;
  }
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(
    target.closest("input, textarea, select, [contenteditable='true']"),
  );
}
