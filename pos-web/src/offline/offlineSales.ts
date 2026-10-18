import { Capacitor } from "@capacitor/core";
import { Network } from "@capacitor/network";
import {
  CapacitorSQLite,
  SQLiteConnection,
  type SQLiteDBConnection,
} from "@capacitor-community/sqlite";

import { api } from "../api/client";
import type { ReceiptSnapshot } from "../printing/types";

const DATABASE_NAME = "apexretail_pos";
const DATABASE_VERSION = 1;
const MAX_SYNC_ATTEMPTS = 20;
const RECEIPT_ARCHIVE_STORAGE_KEY = "apexretail_receipt_archive_v1";

export type OfflineSalePayload = {
  client_sale_id: string;
  client_created_at?: string;
  company_id: string;
  branch_id?: string | null;
  employee_id?: string | null;
  device_id?: string | null;
  device_key?: string | null;
  assignment_revision?: number | null;
  shift_id?: string | null;
  offline_shift_token?: string | null;
  payment_method: string;
  payment_currency_code?: string | null;
  exchange_rate_id?: string | null;
  currency_config_version?: number | null;
  tendered_amount_original?: string | null;
  amount_received?: string;
  discount_amount?: string | null;
  sale_discount_amount?: string | null;
  items: Array<{
    product_id: string;
    variant_id?: string | null;
    quantity: string;
    selling_unit?: string;
    unit_price?: string;
    line_total?: string;
    line_discount_amount?: string | null;
  }>;
};

type OfflineSaleRow = {
  client_sale_id: string;
  payload_json: string;
  status: string;
  attempts: number;
  last_error?: string | null;
  error_code?: string | null;
  error_evidence_json?: string | null;
  quarantined_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type OfflineSyncResult = {
  synced: number;
  failed: number;
  pending: number;
  quarantined: number;
};

export type QuarantinedOfflineSale = {
  client_sale_id: string;
  payload: OfflineSalePayload;
  attempts: number;
  error_code: string;
  last_error: string;
  error_evidence: unknown;
  created_at: string;
  quarantined_at: string;
};

const TERMINAL_AUTHORITY_CODES = new Set([
  "terminal_identity_revoked",
  "terminal_assignment_changed",
  "terminal_decommissioned",
  "offline_shift_closed",
]);

type StoredReceiptRow = {
  sale_id: string;
  receipt_number: string;
  payload_json: string;
  created_at: string;
  updated_at: string;
};

const sqlite = new SQLiteConnection(CapacitorSQLite);

let databaseConnection: SQLiteDBConnection | null = null;
let databaseOpening: Promise<SQLiteDBConnection | null> | null = null;
let synchronizationInProgress: Promise<OfflineSyncResult> | null = null;

export function isAndroidNativeApp(): boolean {
  return Capacitor.getPlatform() === "android";
}

export function createClientSaleId(): string {
  const generated = globalThis.crypto?.randomUUID?.();

  if (generated) {
    return generated;
  }

  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
    /[xy]/g,
    (character) => {
      const random = Math.floor(Math.random() * 16);
      const value =
        character === "x"
          ? random
          : (random & 0x3) | 0x8;

      return value.toString(16);
    },
  );
}

function errorMessage(error: unknown): string {
  const candidate = error as {
    response?: {
      data?: {
        detail?: unknown;
      };
    };
    message?: unknown;
  };

  const detail = candidate?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail.slice(0, 500);
  }

  if (error instanceof Error) {
    return error.message.slice(0, 500);
  }

  if (candidate?.message) {
    return String(candidate.message).slice(0, 500);
  }

  return "Unknown synchronization error";
}

export function isNetworkFailure(error: unknown): boolean {
  const candidate = error as {
    code?: string;
    message?: string;
    response?: unknown;
    request?: unknown;
  };

  return !candidate?.response && (
    Boolean(candidate?.request) ||
    candidate.code === "ERR_NETWORK" ||
    candidate.code === "ECONNABORTED" ||
    candidate.message === "Network Error"
  );
}

export function isTerminalAuthorityFailure(error: unknown): boolean {
  const candidate = error as {
    response?: { data?: { code?: unknown; detail?: { code?: unknown } } };
  };
  const code = candidate?.response?.data?.code || candidate?.response?.data?.detail?.code;
  return typeof code === "string" && TERMINAL_AUTHORITY_CODES.has(code);
}

function synchronizationErrorEvidence(error: unknown) {
  const candidate = error as {
    code?: unknown;
    message?: unknown;
    response?: { status?: unknown; data?: unknown };
  };
  return {
    recorded_at: new Date().toISOString(),
    transport_code: candidate?.code ?? null,
    message: errorMessage(error),
    http_status: candidate?.response?.status ?? null,
    response: candidate?.response?.data ?? null,
  };
}

async function openDatabase(): Promise<SQLiteDBConnection | null> {
  if (!isAndroidNativeApp()) {
    return null;
  }

  if (databaseConnection) {
    const openStatus = await databaseConnection
      .isDBOpen()
      .catch(() => ({ result: false }));

    if (openStatus.result) {
      return databaseConnection;
    }
  }

  if (databaseOpening) {
    return databaseOpening;
  }

  databaseOpening = (async () => {
    await sqlite.checkConnectionsConsistency();

    const existingConnection =
      await sqlite.isConnection(DATABASE_NAME, false);

    const connection = existingConnection.result
      ? await sqlite.retrieveConnection(
          DATABASE_NAME,
          false,
        )
      : await sqlite.createConnection(
          DATABASE_NAME,
          false,
          "no-encryption",
          DATABASE_VERSION,
          false,
        );

    const openStatus = await connection.isDBOpen();

    if (!openStatus.result) {
      await connection.open();
    }

    await connection.execute(`
      CREATE TABLE IF NOT EXISTS offline_sales (
        client_sale_id TEXT PRIMARY KEY NOT NULL,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
    `);

    const offlineColumns = await connection.query(
      "PRAGMA table_info(offline_sales)",
    );
    const columnNames = new Set(
      (offlineColumns.values || []).map((column) => String(column.name)),
    );
    for (const [name, definition] of [
      ["error_code", "TEXT"],
      ["error_evidence_json", "TEXT"],
      ["quarantined_at", "TEXT"],
    ]) {
      if (!columnNames.has(name)) {
        await connection.execute(
          `ALTER TABLE offline_sales ADD COLUMN ${name} ${definition}`,
        );
      }
    }

    await connection.execute(`
      CREATE INDEX IF NOT EXISTS
      idx_offline_sales_status_created
      ON offline_sales(status, created_at);
    `);

    await connection.execute(`
      CREATE TABLE IF NOT EXISTS receipt_archive (
        sale_id TEXT PRIMARY KEY NOT NULL,
        receipt_number TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
    `);

    await connection.execute(`
      CREATE INDEX IF NOT EXISTS
      idx_receipt_archive_receipt_number
      ON receipt_archive(receipt_number);
    `);

    /*
     * An Android process may close while a row is marked
     * "syncing". Return those rows to the pending queue.
     */
    await connection.run(
      `
        UPDATE offline_sales
        SET status = 'pending',
            updated_at = ?
        WHERE status = 'syncing'
      `,
      [new Date().toISOString()],
    );

    databaseConnection = connection;

    return connection;
  })().finally(() => {
    databaseOpening = null;
  });

  return databaseOpening;
}

export async function initializeOfflineSales(): Promise<void> {
  await openDatabase();
}

export async function queueOfflineSale(
  payload: OfflineSalePayload,
): Promise<void> {
  const database = await openDatabase();

  if (!database) {
    throw new Error(
      "Offline sale storage is available only inside the Android app",
    );
  }

  const timestamp = new Date().toISOString();

  await database.run(
    `
      INSERT OR IGNORE INTO offline_sales (
        client_sale_id,
        payload_json,
        status,
        attempts,
        last_error,
        created_at,
        updated_at
      )
      VALUES (?, ?, 'pending', 0, NULL, ?, ?)
    `,
    [
      payload.client_sale_id,
      JSON.stringify(payload),
      timestamp,
      timestamp,
    ],
  );
}

export async function getPendingOfflineSaleCount(): Promise<number> {
  const database = await openDatabase();

  if (!database) {
    return 0;
  }

  const result = await database.query(`
    SELECT COUNT(*) AS total
    FROM offline_sales
    WHERE status IN ('pending', 'failed', 'syncing', 'quarantined')
  `);

  const total = result.values?.[0]?.total;

  return Number(total || 0);
}

export async function getQuarantinedOfflineSales(): Promise<QuarantinedOfflineSale[]> {
  const database = await openDatabase();
  if (!database) return [];

  const result = await database.query(`
    SELECT client_sale_id, payload_json, attempts, last_error, error_code,
           error_evidence_json, created_at, quarantined_at
    FROM offline_sales
    WHERE status = 'quarantined'
    ORDER BY created_at ASC
  `);

  return ((result.values || []) as OfflineSaleRow[]).map((row) => ({
    client_sale_id: row.client_sale_id,
    payload: JSON.parse(row.payload_json) as OfflineSalePayload,
    attempts: Number(row.attempts || 0),
    error_code: row.error_code || "terminal_authority_unknown",
    last_error: row.last_error || "Terminal authority was rejected",
    error_evidence: row.error_evidence_json
      ? JSON.parse(row.error_evidence_json)
      : null,
    created_at: row.created_at,
    quarantined_at: row.quarantined_at || row.updated_at,
  }));
}

export async function exportQuarantinedOfflineSales(): Promise<string> {
  const sales = await getQuarantinedOfflineSales();
  return JSON.stringify(
    {
      format: "apexretail-offline-sale-quarantine-v1",
      exported_at: new Date().toISOString(),
      sales,
    },
    null,
    2,
  );
}

function loadBrowserReceiptArchive(): ReceiptSnapshot[] {
  const rawValue = localStorage.getItem(RECEIPT_ARCHIVE_STORAGE_KEY);

  if (!rawValue) {
    return [];
  }

  try {
    const rows = JSON.parse(rawValue) as ReceiptSnapshot[];
    return Array.isArray(rows) ? rows : [];
  } catch (error) {
    console.error("Failed to load archived receipts", error);
    return [];
  }
}

function saveBrowserReceiptArchive(receipts: ReceiptSnapshot[]) {
  localStorage.setItem(
    RECEIPT_ARCHIVE_STORAGE_KEY,
    JSON.stringify(receipts.slice(0, 200)),
  );
}

export async function archiveReceiptSnapshot(
  receipt: ReceiptSnapshot,
): Promise<void> {
  if (!isAndroidNativeApp()) {
    const current = loadBrowserReceiptArchive().filter(
      (entry) => entry.id !== receipt.id,
    );
    current.unshift(receipt);
    saveBrowserReceiptArchive(current);
    return;
  }

  const database = await openDatabase();

  if (!database) {
    return;
  }

  const timestamp = new Date().toISOString();

  await database.run(
    `
      INSERT OR REPLACE INTO receipt_archive (
        sale_id,
        receipt_number,
        payload_json,
        created_at,
        updated_at
      )
      VALUES (?, ?, ?, ?, ?)
    `,
    [
      receipt.id,
      receipt.receipt_number,
      JSON.stringify(receipt),
      timestamp,
      timestamp,
    ],
  );
}

export async function getArchivedReceiptSnapshot(
  saleId: string,
  receiptNumber?: string,
): Promise<ReceiptSnapshot | null> {
  if (!isAndroidNativeApp()) {
    return (
      loadBrowserReceiptArchive().find(
        (entry) =>
          entry.id === saleId ||
          (receiptNumber && entry.receipt_number === receiptNumber),
      ) || null
    );
  }

  const database = await openDatabase();

  if (!database) {
    return null;
  }

  const result = await database.query(
    `
      SELECT
        sale_id,
        receipt_number,
        payload_json,
        created_at,
        updated_at
      FROM receipt_archive
      WHERE sale_id = ?
         OR receipt_number = ?
      ORDER BY updated_at DESC
      LIMIT 1
    `,
    [saleId, receiptNumber || ""],
  );

  const row = result.values?.[0] as StoredReceiptRow | undefined;

  if (!row?.payload_json) {
    return null;
  }

  try {
    return JSON.parse(row.payload_json) as ReceiptSnapshot;
  } catch (error) {
    console.error("Failed to parse archived receipt", error);
    return null;
  }
}

async function performSynchronization(): Promise<OfflineSyncResult> {
  const database = await openDatabase();

  if (!database) {
    return {
      synced: 0,
      failed: 0,
      pending: 0,
      quarantined: 0,
    };
  }

  const networkStatus = await Network
    .getStatus()
    .catch(() => ({
      connected: false,
      connectionType: "none" as const,
    }));

  if (!networkStatus.connected) {
    return {
      synced: 0,
      failed: 0,
      pending: await getPendingOfflineSaleCount(),
      quarantined: (await getQuarantinedOfflineSales()).length,
    };
  }

  const result = await database.query(
    `
      SELECT
        client_sale_id,
        payload_json,
        status,
        attempts,
        last_error,
        error_code,
        error_evidence_json,
        quarantined_at,
        created_at,
        updated_at
      FROM offline_sales
      WHERE status IN ('pending', 'failed')
        AND attempts < ?
      ORDER BY created_at ASC
      LIMIT 100
    `,
    [MAX_SYNC_ATTEMPTS],
  );

  const rows =
    (result.values || []) as OfflineSaleRow[];

  let synced = 0;
  let failed = 0;

  for (const row of rows) {
    try {
      await database.run(
        `
          UPDATE offline_sales
          SET status = 'syncing',
              attempts = attempts + 1,
              last_error = NULL,
              updated_at = ?
          WHERE client_sale_id = ?
        `,
        [
          new Date().toISOString(),
          row.client_sale_id,
        ],
      );

      const payload =
        JSON.parse(row.payload_json) as OfflineSalePayload;

      /*
       * The backend uses client_sale_id as its idempotency
       * identity. Retrying the same queued sale must not
       * create a second transaction.
       */
      await api.post("/sales", payload);

      await database.run(
        `
          DELETE FROM offline_sales
          WHERE client_sale_id = ?
        `,
        [row.client_sale_id],
      );

      synced += 1;
    } catch (error) {
      failed += 1;

      const quarantined = isTerminalAuthorityFailure(error);
      const evidence = synchronizationErrorEvidence(error);
      const authorityCode = quarantined
        ? String((error as { response?: { data?: { code?: unknown; detail?: { code?: unknown } } } })
            ?.response?.data?.code || (error as { response?: { data?: { detail?: { code?: unknown } } } })
              ?.response?.data?.detail?.code || "")
        : null;
      const timestamp = new Date().toISOString();

      await database.run(
        `
          UPDATE offline_sales
          SET status = ?,
              last_error = ?,
              error_code = ?,
              error_evidence_json = ?,
              quarantined_at = ?,
              updated_at = ?
          WHERE client_sale_id = ?
        `,
        [
          quarantined ? "quarantined" : "failed",
          errorMessage(error),
          authorityCode,
          JSON.stringify(evidence),
          quarantined ? timestamp : null,
          timestamp,
          row.client_sale_id,
        ],
      );

      /*
       * Stop immediately when connectivity was lost again.
       * Remaining rows stay safely inside SQLite.
       */
      if (isNetworkFailure(error)) {
        break;
      }
      if (quarantined) {
        break;
      }
    }
  }

  return {
    synced,
    failed,
    pending: await getPendingOfflineSaleCount(),
    quarantined: (await getQuarantinedOfflineSales()).length,
  };
}

export async function syncPendingOfflineSales():
Promise<OfflineSyncResult> {
  if (!isAndroidNativeApp()) {
    return {
      synced: 0,
      failed: 0,
      pending: 0,
      quarantined: 0,
    };
  }

  if (synchronizationInProgress) {
    return synchronizationInProgress;
  }

  synchronizationInProgress =
    performSynchronization().finally(() => {
      synchronizationInProgress = null;
    });

  return synchronizationInProgress;
}

export async function startAutomaticOfflineSaleSync(
  onResult?: (result: OfflineSyncResult) => void,
): Promise<() => Promise<void>> {
  if (!isAndroidNativeApp()) {
    return async () => undefined;
  }

  await initializeOfflineSales();

  const initialResult =
    await syncPendingOfflineSales();

  onResult?.(initialResult);

  const listener = await Network.addListener(
    "networkStatusChange",
    async (status) => {
      if (!status.connected) {
        onResult?.({
          synced: 0,
          failed: 0,
          pending:
            await getPendingOfflineSaleCount(),
          quarantined: (await getQuarantinedOfflineSales()).length,
        });

        return;
      }

      const syncResult =
        await syncPendingOfflineSales();

      onResult?.(syncResult);
    },
  );

  return async () => {
    await listener.remove();
  };
}
