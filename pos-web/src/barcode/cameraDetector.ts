import readerWasmUrl from "zxing-wasm/reader/zxing_reader.wasm?url";

import { SUPPORTED_BARCODE_FORMATS } from "./barcode";

export type CameraBarcodeDetector = {
  detect(source: HTMLVideoElement): Promise<Array<{ rawValue: string }>>;
};

export async function createCameraBarcodeDetector(): Promise<CameraBarcodeDetector> {
  const { BarcodeDetector, prepareZXingModule } = await import(
    "barcode-detector/ponyfill"
  );
  prepareZXingModule({
    overrides: {
      locateFile: (path: string) =>
        path.endsWith(".wasm") ? readerWasmUrl : path,
    },
  });
  return new BarcodeDetector({ formats: [...SUPPORTED_BARCODE_FORMATS] });
}
