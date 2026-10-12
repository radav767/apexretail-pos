import assert from "node:assert/strict";
import test from "node:test";

import { multiplyDecimalStrings, normalizePositiveDecimal, positiveRateError } from "../src/pages/currencyLogic";

test("decimal conversion preview uses exact string arithmetic", () => {
  assert.equal(multiplyDecimalStrings("10", "18.50", 2), "185.00");
  assert.equal(multiplyDecimalStrings("0.10", "0.20", 4), "0.0200");
  assert.equal(multiplyDecimalStrings("10", "1.23456", 4), "12.3456");
  assert.equal(multiplyDecimalStrings("1", "0.005", 2), "0.01");
});

test("rate validation rejects zero, negative, excessive precision and non-decimals", () => {
  assert.match(positiveRateError("0") || "", /greater than zero/);
  assert.match(positiveRateError("-1") || "", /valid decimal/);
  assert.match(positiveRateError("1.12345678901") || "", /10 decimal places/);
  assert.match(positiveRateError("one") || "", /valid decimal/);
  assert.equal(positiveRateError("18.5000000000"), null);
  assert.equal(normalizePositiveDecimal(" 018.50 "), "18.50");
});
