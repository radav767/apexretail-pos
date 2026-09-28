export type CreditCustomer = {
  id: string;
  company_id: string;
  customer_code: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  active: boolean;
  credit_enabled: boolean;
  unlimited_credit: boolean;
  credit_limit: string | null;
  credit_terms_days: number;
  outstanding_balance: string;
  available_credit: string | null;
};

export type CreditProjection = {
  outstandingBalance: number;
  availableCredit: number | null;
  projectedBalance: number;
  dueDate: string;
  error: string | null;
};

function moneyValue(value: string | number | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function calculateCreditDueDate(
  termsDays: number,
  now = new Date(),
): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Harare",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  const dueDate = new Date(Date.UTC(
    Number(values.year),
    Number(values.month) - 1,
    Number(values.day) + Math.max(0, termsDays),
  ));
  return dueDate.toISOString().slice(0, 10);
}

export function projectCreditSale(
  customer: CreditCustomer | null,
  saleTotal: number,
  now = new Date(),
): CreditProjection {
  if (!customer) {
    return {
      outstandingBalance: 0,
      availableCredit: null,
      projectedBalance: saleTotal,
      dueDate: "",
      error: "Select a customer for this credit sale.",
    };
  }

  const outstandingBalance = moneyValue(customer.outstanding_balance);
  const projectedBalance = outstandingBalance + saleTotal;
  const creditLimit = customer.credit_limit == null
    ? null
    : moneyValue(customer.credit_limit);
  const availableCredit = customer.unlimited_credit
    ? null
    : Math.max(0, moneyValue(customer.available_credit ?? creditLimit));
  let error: string | null = null;

  if (!customer.active) {
    error = "This customer is inactive.";
  } else if (!customer.credit_enabled) {
    error = "Credit is not enabled for this customer.";
  } else if (!customer.unlimited_credit && creditLimit == null) {
    error = "This customer does not have a configured monetary credit limit.";
  } else if (!customer.unlimited_credit && projectedBalance > (creditLimit ?? 0)) {
    error = "This sale would exceed the customer's credit limit.";
  }

  return {
    outstandingBalance,
    availableCredit,
    projectedBalance,
    dueDate: calculateCreditDueDate(customer.credit_terms_days, now),
    error,
  };
}
