import { useEffect, useRef } from "react";

import {
  isEditableTarget,
  KeyboardWedgeDetector,
} from "./keyboardWedge";

export function useKeyboardWedge(
  enabled: boolean,
  onScan: (barcode: string) => void,
) {
  const callbackRef = useRef(onScan);
  callbackRef.current = onScan;

  useEffect(() => {
    if (!enabled) return;
    const detector = new KeyboardWedgeDetector();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) {
        detector.reset();
        return;
      }
      const barcode = detector.feed({
        key: event.key,
        timestamp: event.timeStamp,
        modifier: event.altKey || event.ctrlKey || event.metaKey,
        repeat: event.repeat,
        composing: event.isComposing,
      });
      if (barcode) callbackRef.current(barcode);
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled]);
}
