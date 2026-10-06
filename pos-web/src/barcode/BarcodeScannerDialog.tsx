import { useEffect, useRef, useState } from "react";

import { createDuplicateScanGate } from "./barcode";
import type { CameraBarcodeDetector } from "./cameraDetector";
import { cameraErrorMessage, stopMediaStream } from "./cameraLifecycle";
import "./barcode-scanner.css";

type Props = {
  onScan: (barcode: string) => void;
  onClose: () => void;
  title?: string;
};

export default function BarcodeScannerDialog({
  onScan,
  onClose,
  title = "Scan barcode",
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectorRef = useRef<CameraBarcodeDetector | null>(null);
  const processingRef = useRef(false);
  const acceptedRef = useRef(createDuplicateScanGate());
  const onScanRef = useRef(onScan);
  onScanRef.current = onScan;
  const [status, setStatus] = useState("Starting camera…");
  const [torchSupported, setTorchSupported] = useState(false);
  const [torchOn, setTorchOn] = useState(false);

  function stopCamera() {
    stopMediaStream(streamRef.current);
    streamRef.current = null;
  }

  useEffect(() => {
    let cancelled = false;
    let timer = 0;

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus("Camera scanning is not supported by this browser.");
        return;
      }
      try {
        const [stream, scannerModule] = await Promise.all([
          navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
              facingMode: { ideal: "environment" },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
          }),
          import("./cameraDetector"),
        ]);
        if (cancelled) {
          stopMediaStream(stream);
          return;
        }
        streamRef.current = stream;
        detectorRef.current = await scannerModule.createCameraBarcodeDetector();
        const video = videoRef.current;
        if (!video) throw new Error("Camera preview unavailable");
        video.srcObject = stream;
        await video.play();
        const track = stream.getVideoTracks()[0];
        const capabilities = track?.getCapabilities?.() as MediaTrackCapabilities & {
          torch?: boolean;
        };
        setTorchSupported(Boolean(capabilities?.torch));
        setStatus("Point the camera at a barcode");

        timer = window.setInterval(async () => {
          if (cancelled || processingRef.current || video.readyState < 2) return;
          processingRef.current = true;
          try {
            const results = await detectorRef.current?.detect(video);
            const accepted = results?.[0]?.rawValue
              ? acceptedRef.current(results[0].rawValue)
              : null;
            if (accepted) {
              cancelled = true;
              window.clearInterval(timer);
              stopCamera();
              onScanRef.current(accepted);
            }
          } catch {
            // A frame without a decodable barcode is expected during scanning.
          } finally {
            processingRef.current = false;
          }
        }, 160);
      } catch (error) {
        stopCamera();
        setStatus(cameraErrorMessage(error));
      }
    }

    void start();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      stopCamera();
    };
  }, []);

  async function toggleTorch() {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track || !torchSupported) return;
    const next = !torchOn;
    try {
      await track.applyConstraints({
        advanced: [{ torch: next } as MediaTrackConstraintSet],
      });
      setTorchOn(next);
    } catch {
      setTorchSupported(false);
      setStatus("Torch is not supported by this camera.");
    }
  }

  return (
    <div className="barcode-scanner-backdrop" role="presentation">
      <section
        className="barcode-scanner-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="barcode-scanner-title"
      >
        <header>
          <h2 id="barcode-scanner-title">{title}</h2>
          <button type="button" aria-label="Close barcode scanner" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="barcode-scanner-preview">
          <video ref={videoRef} muted playsInline />
          <div className="barcode-scanner-guide" aria-hidden="true" />
        </div>
        <p className="barcode-scanner-status" role="status" aria-live="polite">
          {status}
        </p>
        <footer>
          {torchSupported && (
            <button type="button" onClick={() => void toggleTorch()}>
              {torchOn ? "Turn torch off" : "Turn torch on"}
            </button>
          )}
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
        </footer>
      </section>
    </div>
  );
}
