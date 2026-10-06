export function cameraErrorMessage(error: unknown): string {
  const name = (error as { name?: string })?.name;
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Camera permission was denied. Allow camera access and try again.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No usable camera was found on this device.";
  }
  if (name === "NotReadableError") {
    return "The camera is already in use by another application.";
  }
  return "Camera barcode scanning is unavailable on this device.";
}

export function stopMediaStream(stream: MediaStream | null): void {
  for (const track of stream?.getTracks() || []) track.stop();
}
