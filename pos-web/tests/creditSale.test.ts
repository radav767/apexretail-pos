import assert from "node:assert/strict";
import {
  calculateCreditDueDate,
  projectCreditSale,
  type CreditCustomer,
} from "../src/creditSale.ts";

function customer(overrides: Partial<CreditCustomer> = {}): CreditCustomer {
  return {
    id: "customer-1",
    company_id: "company-1",
    customer_code: "C-001",
    name: "Credit Customer",
    active: true,
    credit_enabled: true,
    unlimited_credit: false,
    credit_limit: "100.00",
    credit_terms_days: 30,
    outstanding_balance: "25.00",
    available_credit: "75.00",
    ...overrides,
  };
}

assert.match(projectCreditSale(null, 10).error || "", /Select a customer/);
assert.match(projectCreditSale(customer({ credit_enabled: false }), 10).error || "", /not enabled/);
assert.match(projectCreditSale(customer({ active: false }), 10).error || "", /inactive/);
assert.match(projectCreditSale(customer(), 80).error || "", /exceed/);

const limited = projectCreditSale(customer(), 50, new Date("2026-09-26T10:00:00Z"));
assert.equal(limited.error, null);
assert.equal(limited.outstandingBalance, 25);
assert.equal(limited.availableCredit, 75);
assert.equal(limited.projectedBalance, 75);
assert.equal(limited.dueDate, "2026-10-26");

const unlimited = projectCreditSale(customer({
  unlimited_credit: true,
  credit_limit: null,
  available_credit: null,
}), 10_000);
assert.equal(unlimited.error, null);
assert.equal(unlimited.availableCredit, null);
assert.equal(unlimited.projectedBalance, 10_025);

const implicitUnlimited = projectCreditSale(customer({
  unlimited_credit: false,
  credit_limit: null,
  available_credit: null,
}), 10);
assert.match(implicitUnlimited.error || "", /configured monetary credit limit/);
assert.equal(calculateCreditDueDate(0, new Date("2026-09-26T10:00:00Z")), "2026-09-26");

console.log("PASS: customer required, disabled/inactive/limit rejection, explicit unlimited credit, projections and due dates");
