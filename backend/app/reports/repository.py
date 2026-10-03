from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Branch, Category, Employee, Product, Shop


class ReportsRepository:
    DIMENSIONS = {
        "shop_id": Shop, "branch_id": Branch, "cashier_id": Employee,
        "product_id": Product, "category_id": Category,
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_dimensions(self, company_id, values):
        for key, model in self.DIMENSIONS.items():
            value = values.get(key)
            if value is None:
                continue
            result = await self.db.execute(
                select(model.id).where(model.id == value, model.company_id == company_id)
            )
            if result.scalar_one_or_none() is None:
                return key
        return None

    async def options(self, company_id):
        async def rows(sql):
            result = await self.db.execute(text(sql), {"company_id": company_id})
            return [dict(row) for row in result.mappings().all()]
        return {
            "shops": await rows("SELECT id, name FROM shops WHERE company_id=:company_id AND deleted=false ORDER BY name"),
            "branches": await rows("SELECT id, name FROM branches WHERE company_id=:company_id AND deleted=false ORDER BY name"),
            "cashiers": await rows("SELECT id, name FROM employees WHERE company_id=:company_id AND deleted=false ORDER BY name"),
            "products": await rows("SELECT id, name FROM products WHERE company_id=:company_id AND deleted=false ORDER BY name"),
            "categories": await rows("SELECT id, name FROM categories WHERE company_id=:company_id AND deleted=false ORDER BY name"),
        }

    @staticmethod
    def _filters(query):
        clauses = ["s.company_id=:company_id", "s.created_at>=:start_at", "s.created_at<:end_at"]
        mapping = {
            "shop_id": "s.shop_id", "branch_id": "s.branch_id",
            "cashier_id": "s.employee_id", "payment_method": "LOWER(s.payment_method)",
        }
        for key, column in mapping.items():
            if getattr(query, key) is not None:
                clauses.append(f"{column}=:{key}")
        if query.product_id is not None:
            clauses.append("EXISTS (SELECT 1 FROM sale_items fsi WHERE fsi.sale_id=s.id AND fsi.product_id=:product_id)")
        if query.category_id is not None:
            clauses.append("EXISTS (SELECT 1 FROM sale_items fsi WHERE fsi.sale_id=s.id AND fsi.category_id_snapshot=:category_id)")
        if query.view == "credit_sales":
            clauses.extend(["s.original_sale_id IS NULL", "LOWER(s.payment_method)='credit'", "LOWER(s.status) IN ('completed','partially_refunded','refunded')"])
        elif query.view == "refunds_cancellations":
            clauses.append("((s.original_sale_id IS NOT NULL AND LOWER(s.status)='refunded') OR LOWER(s.status) IN ('cancelled','canceled','voided'))")
        else:
            clauses.append("((s.original_sale_id IS NULL AND LOWER(s.status) IN ('completed','partially_refunded','refunded','cancelled','canceled','voided')) OR (s.original_sale_id IS NOT NULL AND LOWER(s.status)='refunded'))")
        return " AND ".join(clauses)

    @staticmethod
    def _cte(query):
        return f"""
        WITH eligible_sales AS (SELECT s.* FROM sales s WHERE {ReportsRepository._filters(query)}),
        item_totals AS (
          SELECT si.sale_id, COALESCE(SUM(si.line_total),0) line_amount,
            COALESCE(SUM(si.line_cost),0) cost,
            BOOL_AND(si.cost_snapshot_available IS TRUE) cost_known
          FROM sale_items si JOIN eligible_sales s ON s.id=si.sale_id GROUP BY si.sale_id
        ), tx AS (
          SELECT s.*,
            COALESCE(it.line_amount,0) line_amount,
            CASE WHEN LOWER(s.status) IN ('cancelled','canceled','voided') THEN 0 ELSE COALESCE(it.cost,0) END cost,
            CASE WHEN LOWER(s.status) IN ('cancelled','canceled','voided') THEN true ELSE COALESCE(it.cost_known,false) END cost_known,
            CASE WHEN s.original_sale_id IS NOT NULL THEN s.total_amount
                 WHEN LOWER(s.status) IN ('cancelled','canceled','voided') THEN 0
                 ELSE s.total_amount END amount,
            CASE WHEN s.original_sale_id IS NOT NULL THEN -s.total_amount ELSE 0 END refunds,
            CASE WHEN s.original_sale_id IS NULL AND LOWER(s.status) NOT IN ('cancelled','canceled','voided') THEN s.total_amount ELSE 0 END gross_sales,
            CASE WHEN LOWER(s.status) IN ('cancelled','canceled','voided') OR s.original_sale_id IS NOT NULL THEN true
                 ELSE s.discount_amount IS NOT NULL END discount_known,
            CASE WHEN s.original_sale_id IS NULL AND LOWER(s.status) NOT IN ('cancelled','canceled','voided')
                 THEN s.discount_amount ELSE 0 END discount
          FROM eligible_sales s LEFT JOIN item_totals it ON it.sale_id=s.id
        )
        """

    @classmethod
    def sales_history_rows_sql(cls, query):
        """Return the exact grouped population used by screen, CSV, and plans."""
        grouped = query.view in {"cashier", "payment_type", "shop_branch"}
        item_grouped = query.view in {"product", "category"}
        if item_grouped:
            if query.view == "product":
                key, label = "si.product_id", "si.product_name"
            else:
                key = "si.category_id_snapshot"
                label = "COALESCE(si.category_name_snapshot,'Unavailable')"
            item_filters = []
            if query.product_id is not None:
                item_filters.append("si.product_id=:product_id")
            if query.category_id is not None:
                item_filters.append("si.category_id_snapshot=:category_id")
            item_where = (
                " WHERE " + " AND ".join(item_filters)
                if item_filters else ""
            )
            base = cls._cte(query) + f"""
              SELECT {key} dimension_id, {label} label,
                COUNT(DISTINCT tx.id) transactions,
                COALESCE(SUM(CASE WHEN LOWER(tx.status) IN ('cancelled','canceled','voided') THEN 0 WHEN tx.original_sale_id IS NOT NULL THEN -si.quantity ELSE si.quantity END),0) quantity,
                COALESCE(SUM(CASE
                  WHEN LOWER(tx.status) IN ('cancelled','canceled','voided') THEN 0
                  WHEN COALESCE(tx.line_amount,0)=0 THEN 0
                  ELSE tx.amount * si.line_total / tx.line_amount
                END),0) amount,
                COALESCE(SUM(CASE WHEN LOWER(tx.status) IN ('cancelled','canceled','voided') THEN 0 ELSE si.line_cost END),0) cost,
                BOOL_AND(LOWER(tx.status) IN ('cancelled','canceled','voided') OR si.cost_snapshot_available IS TRUE) cost_known,
                false discount_known, NULL::numeric discount
              FROM tx JOIN sale_items si ON si.sale_id=tx.id{item_where}
              GROUP BY {key}, {label}
            """
        elif grouped:
            dimensions = {
                "cashier": (
                    "tx.employee_id",
                    "COALESCE(NULLIF(tx.cashier_name,''),'Unassigned')",
                ),
                "payment_type": (
                    "NULL::uuid",
                    "COALESCE(NULLIF(LOWER(tx.payment_method),''),'unknown')",
                ),
                "shop_branch": (
                    "tx.branch_id",
                    "COALESCE(NULLIF(tx.branch_name_snapshot,''),NULLIF(tx.shop_name_snapshot,''),'Unassigned')",
                ),
            }
            key, label = dimensions[query.view]
            base = cls._cte(query) + f"""
              SELECT {key} dimension_id, {label} label, COUNT(*) transactions,
                NULL::numeric quantity, COALESCE(SUM(tx.amount),0) amount,
                COALESCE(SUM(tx.cost),0) cost, BOOL_AND(tx.cost_known) cost_known,
                BOOL_AND(tx.discount_known) discount_known, SUM(tx.discount) discount
              FROM tx GROUP BY {key}, {label}
            """
        else:
            label = (
                "tx.receipt_number || ' — ' || COALESCE(NULLIF(tx.customer_name_snapshot,''),'Legacy / Unassigned')"
                if query.view == "credit_sales" else "tx.receipt_number"
            )
            base = cls._cte(query) + f"""
              SELECT tx.id dimension_id, {label} label, 1 transactions,
                NULL::numeric quantity, tx.amount, tx.cost, tx.cost_known,
                tx.discount_known, tx.discount,
                tx.created_at, tx.payment_method, tx.status, tx.cashier_name,
                COALESCE(tx.branch_name_snapshot,tx.shop_name_snapshot,'Unassigned') branch_name
              FROM tx
            """
        allowed = {
            "amount": "amount", "label": "label",
            "transactions": "transactions", "quantity": "quantity",
            "date": "created_at",
        }
        sort = allowed.get(query.sort_by, "amount")
        if (grouped or item_grouped) and sort == "created_at":
            sort = "amount"
        direction = "ASC" if query.sort_dir == "asc" else "DESC"
        return base, sort, direction

    async def sales_history(self, company_id, query, start_at, end_at, *, export=False):
        params = query.model_dump()
        params.update(company_id=company_id, start_at=start_at, end_at=end_at)
        if params.get("payment_method") is not None:
            params["payment_method"] = params["payment_method"].strip().lower()
        base, sort, direction = self.sales_history_rows_sql(query)
        count_result = await self.db.execute(text(f"SELECT COUNT(*) FROM ({base}) report_rows"), params)
        total = int(count_result.scalar_one() or 0)
        page_limit = min(total, 10000) if export else query.limit
        page_offset = 0 if export else query.offset
        rows_result = await self.db.execute(
            text(f"SELECT * FROM ({base}) report_rows ORDER BY {sort} {direction} NULLS LAST, label ASC, dimension_id ASC NULLS LAST LIMIT :page_limit OFFSET :page_offset"),
            {**params, "page_limit": page_limit, "page_offset": page_offset},
        )
        summary_result = await self.db.execute(text(self._cte(query) + """
          SELECT COALESCE(SUM(gross_sales),0) gross_sales, COALESCE(SUM(refunds),0) refunds,
            COALESCE(SUM(amount),0) net_sales, COALESCE(SUM(cost),0) cost,
            BOOL_AND(cost_known) cost_known,
            BOOL_AND(discount_known) discount_known, SUM(discount) discount,
            COUNT(*) transactions FROM tx
        """), params)
        return total, [dict(row) for row in rows_result.mappings().all()], dict(summary_result.mappings().one())

    async def valuation(self, company_id, *, branch_id=None, category_id=None, product_id=None, limit=50, offset=0, export=False):
        clauses = ["ib.company_id=:company_id", "ib.active=true", "ib.deleted=false", "p.active=true", "p.deleted=false"]
        params = {"company_id": company_id, "branch_id": branch_id, "category_id": category_id, "product_id": product_id}
        for key, column in (("branch_id","ib.branch_id"),("category_id","p.category_id"),("product_id","p.id")):
            if params[key] is not None: clauses.append(f"{column}=:{key}")
        where = " AND ".join(clauses)
        sql = f"""SELECT p.id product_id,p.name product_name,p.sku,p.selling_price,p.cost_price,
          ib.quantity,b.id branch_id,b.name branch_name,sh.id shop_id,sh.name shop_name
          FROM inventory_balances ib JOIN products p ON p.id=ib.product_id AND p.company_id=ib.company_id
          JOIN branches b ON b.id=ib.branch_id AND b.company_id=ib.company_id
          JOIN shops sh ON sh.id=ib.shop_id AND sh.company_id=ib.company_id WHERE {where}"""
        count = await self.db.execute(text(f"SELECT COUNT(*) FROM ({sql}) valuation_rows"), params)
        total = int(count.scalar_one() or 0)
        result = await self.db.execute(text(sql + " ORDER BY p.name,b.name LIMIT :limit OFFSET :offset"), {**params,"limit":min(total,10000) if export else limit,"offset":0 if export else offset})
        summary_result = await self.db.execute(text(f"""SELECT COALESCE(SUM(quantity),0) quantity,
          COALESCE(SUM(quantity*selling_price),0) selling_value,
          COALESCE(SUM(quantity*cost_price),0) cost_value,
          COALESCE(BOOL_AND(selling_price IS NOT NULL),true) selling_known,
          COALESCE(BOOL_AND(cost_price IS NOT NULL),true) cost_known FROM ({sql}) valuation_rows"""), params)
        return total, [dict(row) for row in result.mappings().all()], dict(summary_result.mappings().one())

    async def currency(self, company_id):
        result = await self.db.execute(text("SELECT currency_symbol,decimal_places FROM company_settings WHERE company_id=:company_id"), {"company_id": company_id})
        row = result.mappings().first()
        return (row["currency_symbol"], int(row["decimal_places"])) if row else ("$", 2)

    async def financial_summary(self, company_id, start_at, end_at, branch_id=None, shop_id=None):
        params = {"company_id": company_id, "start_at": start_at, "end_at": end_at, "branch_id": branch_id, "shop_id": shop_id}
        branch_sale = "AND (CAST(:branch_id AS uuid) IS NULL OR s.branch_id=CAST(:branch_id AS uuid))"
        branch_expense = "AND (CAST(:branch_id AS uuid) IS NULL OR e.branch_id=CAST(:branch_id AS uuid))"
        branch_settlement = "AND (CAST(:branch_id AS uuid) IS NULL OR cs.branch_id=CAST(:branch_id AS uuid))"
        branch_receivable = "AND (CAST(:branch_id AS uuid) IS NULL OR cr.branch_id=CAST(:branch_id AS uuid))"
        shop_sale = "AND (CAST(:shop_id AS uuid) IS NULL OR s.shop_id=CAST(:shop_id AS uuid))"
        shop_expense = "AND (CAST(:shop_id AS uuid) IS NULL OR e.shop_id=CAST(:shop_id AS uuid))"
        shop_settlement = "AND (CAST(:shop_id AS uuid) IS NULL OR cs.shop_id=CAST(:shop_id AS uuid))"
        shop_receivable = "AND (CAST(:shop_id AS uuid) IS NULL OR cr.shop_id=CAST(:shop_id AS uuid))"
        result = await self.db.execute(text(f"""
            WITH eligible_sales AS (
                SELECT s.id,s.total_amount,s.payment_method,s.original_sale_id,s.discount_amount
                  FROM sales s
                 WHERE s.company_id=:company_id
                   AND s.created_at>=:start_at AND s.created_at<:end_at
                   {branch_sale} {shop_sale}
                   AND ((s.original_sale_id IS NULL AND lower(s.status) IN ('completed','partially_refunded','refunded'))
                     OR (s.original_sale_id IS NOT NULL AND lower(s.status)='refunded'))
            ), sale_costs AS (
                SELECT COALESCE(SUM(si.line_cost),0) cost_of_sales
                  FROM sale_items si JOIN eligible_sales es ON es.id=si.sale_id
            ), sale_totals AS (
                SELECT COALESCE(SUM(CASE WHEN original_sale_id IS NULL THEN total_amount ELSE 0 END),0) gross_sales,
                       COALESCE(SUM(total_amount),0) net_sales,
                       COALESCE(SUM(CASE WHEN original_sale_id IS NULL THEN discount_amount ELSE 0 END),0) discounts,
                       COALESCE(SUM(CASE WHEN lower(payment_method)='cash' THEN total_amount ELSE 0 END),0) cash_sales,
                       COALESCE(SUM(CASE WHEN lower(payment_method)='card' THEN total_amount ELSE 0 END),0) card_sales,
                       COALESCE(SUM(CASE WHEN lower(payment_method)='mobile' THEN total_amount ELSE 0 END),0) mobile_sales,
                       COALESCE(SUM(CASE WHEN lower(payment_method)='credit' THEN total_amount ELSE 0 END),0) credit_sales
                  FROM eligible_sales
            ), expense_totals AS (
                SELECT COALESCE(SUM(e.amount),0) operating_expenses,
                       COALESCE(SUM(CASE WHEN lower(e.payment_method)='cash' THEN e.amount ELSE 0 END),0) cash_expenses,
                       COALESCE(SUM(CASE WHEN lower(e.payment_method)='card' THEN e.amount ELSE 0 END),0) card_expenses,
                       COALESCE(SUM(CASE WHEN lower(e.payment_method)='mobile' THEN e.amount ELSE 0 END),0) mobile_expenses
                  FROM expenses e WHERE e.company_id=:company_id
                   AND e.occurred_at>=:start_at AND e.occurred_at<:end_at {branch_expense} {shop_expense}
            ), settlement_totals AS (
                SELECT COALESCE(SUM(cs.amount),0) credit_settlements,
                       COALESCE(SUM(CASE WHEN lower(cs.payment_method)='cash' THEN cs.amount ELSE 0 END),0) cash_settlements,
                       COALESCE(SUM(CASE WHEN lower(cs.payment_method)='card' THEN cs.amount ELSE 0 END),0) card_settlements,
                       COALESCE(SUM(CASE WHEN lower(cs.payment_method)='mobile' THEN cs.amount ELSE 0 END),0) mobile_settlements
                  FROM credit_settlements cs WHERE cs.company_id=:company_id
                   AND cs.received_at>=:start_at AND cs.received_at<:end_at {branch_settlement} {shop_settlement}
            ), receivable_totals AS (
                SELECT COALESCE(SUM(cr.outstanding_balance),0) outstanding_receivables
                  FROM credit_receivables cr WHERE cr.company_id=:company_id
                   {branch_receivable} {shop_receivable}
            )
            SELECT st.gross_sales,st.net_sales,sc.cost_of_sales,
                   st.net_sales-sc.cost_of_sales gross_profit,
                   st.discounts,
                   et.operating_expenses,
                   st.net_sales-sc.cost_of_sales-et.operating_expenses net_profit,
                   st.cash_sales,st.card_sales,st.mobile_sales,st.credit_sales,
                   sett.credit_settlements,rt.outstanding_receivables,
                   sett.cash_settlements,et.cash_expenses,
                   st.cash_sales+sett.cash_settlements-et.cash_expenses expected_cash_movement,
                   sett.card_settlements,sett.mobile_settlements,
                   et.card_expenses,et.mobile_expenses
              FROM sale_totals st CROSS JOIN sale_costs sc
              CROSS JOIN expense_totals et CROSS JOIN settlement_totals sett
              CROSS JOIN receivable_totals rt
        """), params)
        return dict(result.mappings().one())
