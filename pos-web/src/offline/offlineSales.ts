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
  company_id: string;
  branch_id?: string | null;
  employee_id?: string | null;
  device_id?: string | null;
  device_key?: string | null;
  payment_method: string;
  amount_received?: string;
  discount_amount?: string | null;
  sale_discount_amount?: string | null;
  items: Array<{
    product_id: string;
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
  created_at: string;
  updated_at: string;
};

export type OfflineSyncResult = {
  synced: number;
  failed: number;
  pending: number;
};

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
  if (error instanceof Error) {
    return error.message.slice(0, 500);
  }

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
  };

  if (!candidate?.response) {
    return true;
  }

  return (
    candidate.code === "ERR_NETWORK" ||
    candidate.code === "ECONNABORTED" ||
    candidate.message === "Network Error"
  );
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
    WHERE status IN ('pending', 'failed', 'syncing')
  `);

  const total = result.values?.[0]?.total;

  return Number(total || 0);
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

      await database.run(
        `
          UPDATE offline_sales
          SET status = 'failed',
              last_error = ?,
              updated_at = ?
          WHERE client_sale_id = ?
        `,
        [
          errorMessage(error),
          new Date().toISOString(),
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
    }
  }

  return {
    synced,
    failed,
    pending: await getPendingOfflineSaleCount(),
  };
}

export async function syncPendingOfflineSales():
Promise<OfflineSyncResult> {
  if (!isAndroidNativeApp()) {
    return {
      synced: 0,
      failed: 0,
      pending: 0,
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
