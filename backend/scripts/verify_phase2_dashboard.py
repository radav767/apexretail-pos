#!/usr/bin/env python3
"""Verify the authenticated Phase 2 Dashboard response against PostgreSQL."""

import json
import os
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg2
from dotenv import dotenv_values
from sqlalchemy.engine import make_url


ENV_FILE = "/root/apexretail-pos/backend/.env"
REPORTING_TIMEZONE = "Africa/Harare"


def synchronous_database_url(database_url: str) -> str:
    """Return the application URL with the synchronous psycopg2 dialect."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )


def verify_dashboard(response_file: str, company_id: str, database_url: str) -> None:
    with open(response_file, encoding="utf-8") as response:
        body = json.load(response)

    if (
        body.get("range_key") != "today"
        or body.get("reporting_timezone") != REPORTING_TIMEZONE
    ):
        raise SystemExit("Dashboard range/timezone mismatch")

    metrics = body.get("metrics", {})
    expected_metric_names = {
        "gross_sales",
        "net_sales",
        "cost_of_sales",
        "gross_profit",
        "discounts",
        "refunds",
    }
    if set(metrics) != expected_metric_names:
        raise SystemExit("Dashboard metric set mismatch")

    reporting_timezone = ZoneInfo(REPORTING_TIMEZONE)
    day = datetime.now(reporting_timezone).date()
    start = datetime.combine(day, time.min, tzinfo=reporting_timezone).astimezone(
        timezone.utc
    )
    end = datetime.combine(
        day + timedelta(days=1), time.min, tzinfo=reporting_timezone
    ).astimezone(timezone.utc)

    connection = psycopg2.connect(synchronous_database_url(database_url))
    with connection, connection.cursor() as query:
        query.execute(
            """WITH tx AS (SELECT * FROM sales s WHERE s.company_id=%s AND s.created_at >= %s
              AND s.created_at < %s AND ((s.original_sale_id IS NULL AND lower(s.status) IN
              ('completed','partially_refunded','refunded')) OR
              (s.original_sale_id IS NOT NULL AND lower(s.status)='refunded'))),
              sales AS (SELECT COALESCE(sum(total_amount) FILTER(WHERE original_sale_id IS NULL),0) gross,
              COALESCE(-sum(total_amount) FILTER(WHERE original_sale_id IS NOT NULL),0) refunds,
              COALESCE(sum(discount_amount) FILTER(WHERE original_sale_id IS NULL),0) discounts,
              count(*) FILTER(WHERE original_sale_id IS NULL) originals,
              count(discount_amount) FILTER(WHERE original_sale_id IS NULL) known FROM tx),
              costs AS (SELECT COALESCE(sum(i.line_cost),0) cost FROM sale_items i JOIN tx ON tx.id=i.sale_id)
              SELECT gross,refunds,gross-refunds,cost,gross-refunds-cost,discounts,originals=known FROM sales,costs""",
            (company_id, start, end),
        )
        gross, refunds, net, cost, profit, discounts, known = query.fetchone()

    expected = {
        "gross_sales": gross,
        "refunds": refunds,
        "net_sales": net,
        "cost_of_sales": cost,
        "gross_profit": profit,
    }
    for name, value in expected.items():
        metric = metrics[name]
        if not metric.get("available") or Decimal(str(metric.get("value"))) != Decimal(
            value
        ).quantize(Decimal(".01")):
            raise SystemExit(f"Dashboard {name} mismatch")

    discount_metric = metrics["discounts"]
    if bool(discount_metric.get("available")) != bool(known):
        raise SystemExit("Dashboard discount availability mismatch")
    if known and Decimal(str(discount_metric.get("value"))) != Decimal(
        discounts
    ).quantize(Decimal(".01")):
        raise SystemExit("Dashboard discounts mismatch")


def main() -> None:
    response_file = os.environ["DASHBOARD_RESPONSE"]
    company_id = os.environ["EXPECTED_DASHBOARD_COMPANY_ID"]
    database_url = dotenv_values(ENV_FILE)["DATABASE_URL"]
    verify_dashboard(response_file, company_id, database_url)


if __name__ == "__main__":
    main()
