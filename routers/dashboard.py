from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from database import get_db
from models import Transaction, Product, Inventory, User, Store, Submission
from routers.auth import get_current_user
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# ────────────────────────────────────────────────────────────
# Access control
# ────────────────────────────────────────────────────────────

def apply_role_filter(query, user, model):
    if user["role"] == "manager":
        if not user["store_id"]:
            raise HTTPException(status_code=403, detail="No store assigned to this account")
        return query.filter(model.store_id == user["store_id"])
    return query




def get_current_iso_week() -> tuple[int, int]:
    today = date.today()
    iso = today.isocalendar()
    return iso[0], iso[1]


def prev_iso_week(iso_year: int, iso_week: int) -> tuple[int, int]:
    jan4 = date(iso_year, 1, 4)
    monday = jan4 + timedelta(weeks=iso_week - 1) - timedelta(days=jan4.weekday())
    prev_monday = monday - timedelta(weeks=1)
    iso = prev_monday.isocalendar()
    return iso[0], iso[1]


def iso_weeks_in_year(year: int) -> int:
    jan1_dow = date(year, 1, 1).weekday()
    dec31_dow = date(year, 12, 31).weekday()
    return 53 if jan1_dow == 3 or dec31_dow == 3 else 52


def week_label(iso_year: int, iso_week: int) -> str:
    jan4 = date(iso_year, 1, 4)
    monday = jan4 + timedelta(weeks=iso_week - 1) - timedelta(days=jan4.weekday())
    month_name = monday.strftime("%b %Y")
    return f"Week {iso_week} · {month_name}"


def resolve_week(iso_year: int | None, iso_week: int | None) -> tuple[int, int]:
    if iso_year and iso_week:
        return iso_year, iso_week
    return get_current_iso_week()


def _all_weeks_between(
    start_year: int, start_week: int,
    end_year: int,   end_week: int,
) -> list[tuple[int, int]]:
    weeks = []
    y, w = end_year, end_week
    while (y, w) >= (start_year, start_week):
        weeks.append((y, w))
        w -= 1
        if w == 0:
            y -= 1
            w = iso_weeks_in_year(y)
    return weeks


# ────────────────────────────────────────────────────────────
# Metrics
# ────────────────────────────────────────────────────────────

def pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


def get_week_metric(db: Session, user: dict, iso_year: int, iso_week: int, agg_expr):
    query = (
        db.query(agg_expr)
        .join(Submission, Submission.submission_id == Transaction.submission_id)
        .filter(
            extract("isoyear", Submission.week_start) == iso_year,
            extract("week",    Submission.week_start) == iso_week,
            Submission.status == "active",
        )
    )
    query = apply_role_filter(query, user, Transaction)
    return query.scalar() or 0


def get_store_info(db: Session, store_id: int | None) -> tuple[str | None, str | None]:
    if not store_id:
        return None, None
    store = db.query(Store).filter(Store.store_id == store_id).first()
    if not store:
        return None, None
    return store.store_name, store.location


# ── /me ──────────────────────────────────────────────────
@router.get("/me")
def get_me(user=Depends(get_current_user)):
    return user


# ── /summary ─────────────────────────────────────────────
@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    iso_year: int | None = None,
    iso_week: int | None = None,
):

    try:
        # All-time totals
        total_revenue_query = apply_role_filter(
            db.query(func.sum(Transaction.total_price)), user, Transaction
        )
        total_revenue = float(total_revenue_query.scalar() or 0)

        total_transactions_query = apply_role_filter(
            db.query(func.count(Transaction.transaction_id)), user, Transaction
        )
        total_transactions = int(total_transactions_query.scalar() or 0)

        avg_basket_query = apply_role_filter(
            db.query(func.avg(Transaction.total_price)), user, Transaction
        )
        avg_basket = float(round(avg_basket_query.scalar() or 0, 2))

        stock_alert_query = apply_role_filter(
            db.query(func.count(Inventory.inventory_id)).filter(
                Inventory.stock_quantity < Inventory.reorder_level
            ),
            user, Inventory,
        )
        stock_alert_count = int(stock_alert_query.scalar() or 0)

        # This week vs last week
        cur_year, cur_week = resolve_week(iso_year, iso_week)
        prv_year, prv_week = prev_iso_week(cur_year, cur_week)

        cur_revenue = float(get_week_metric(
            db, user, cur_year, cur_week, func.sum(Transaction.total_price)))
        prv_revenue = float(get_week_metric(
            db, user, prv_year, prv_week, func.sum(Transaction.total_price)))

        cur_transactions = int(get_week_metric(
            db, user, cur_year, cur_week, func.count(Transaction.transaction_id)))
        prv_transactions = int(get_week_metric(
            db, user, prv_year, prv_week, func.count(Transaction.transaction_id)))

        cur_avg_basket = float(round(get_week_metric(
            db, user, cur_year, cur_week, func.avg(Transaction.total_price)), 2))
        prv_avg_basket = float(round(get_week_metric(
            db, user, prv_year, prv_week, func.avg(Transaction.total_price)), 2))

        # Has this store filed its submission for the current week yet?
        week_submitted = False
        if user["role"] == "manager" and user["store_id"]:
            submission = db.query(Submission).filter(
                Submission.store_id == user["store_id"],
                extract("isoyear", Submission.week_start) == cur_year,
                extract("week",    Submission.week_start) == cur_week,
                Submission.status == "active",
            ).first()
            week_submitted = submission is not None

        user_profile = db.query(User).filter(User.id == user["id"]).first()
        user_name = user_profile.username if user_profile else None

        store_name, store_location = get_store_info(db, user["store_id"])

        return {
            "total_revenue":          total_revenue,
            "total_transactions":     total_transactions,
            "avg_basket":             avg_basket,
            "stock_alert_count":      stock_alert_count,
            "week_number":            cur_week,
            "week_label":             week_label(cur_year, cur_week),
            "week_submitted":         week_submitted,
            "week_revenue":           cur_revenue,
            "week_transactions":      cur_transactions,
            "week_avg_basket":        cur_avg_basket,
            "revenue_delta_pct":      pct_change(cur_revenue, prv_revenue),
            "transactions_delta_pct": pct_change(cur_transactions, prv_transactions),
            "avg_basket_delta_pct":   pct_change(cur_avg_basket, prv_avg_basket),
            "store_id":               user["store_id"],
            "store_name":             store_name,
            "store_location":         store_location,
            "user_name":              user_name,
            "role":                   user["role"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard summary")


# ── /revenue-trend ────────────────────────────────────────
@router.get("/revenue-trend")
def get_revenue_trend(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    try:
        cur_year, cur_week = get_current_iso_week()

        cutoff_year, cutoff_week = cur_year, cur_week
        for _ in range(8):
            cutoff_year, cutoff_week = prev_iso_week(cutoff_year, cutoff_week)

        period_year = extract("isoyear", Submission.week_start).label("period_year")
        period_week = extract("week",    Submission.week_start).label("period_week")

        query = (
            db.query(
                period_year,
                period_week,
                func.sum(Transaction.total_price).label("revenue"),
            )
            .join(Submission, Submission.submission_id == Transaction.submission_id)
            .filter(
                Submission.status == "active",
                (extract("isoyear", Submission.week_start) > cutoff_year) |
                (
                    (extract("isoyear", Submission.week_start) == cutoff_year) &
                    (extract("week",    Submission.week_start) >= cutoff_week)
                )
            )
        )

        if user["role"] == "manager":
            if not user["store_id"]:
                raise HTTPException(status_code=403, detail="No store assigned")
            query = query.filter(Transaction.store_id == user["store_id"])

        results = (
            query
            .group_by(period_year, period_week)
            .order_by(period_year, period_week)
            .all()
        )

        return {
            "data": [
                {
                    "date":    f"W{int(row.period_week)}",
                    "revenue": float(row.revenue),
                }
                for row in results
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Revenue trend error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load revenue trend")


# ── /ops-summary ──────────────────────────────────────────
@router.get("/ops-summary")
def get_ops_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    iso_year: int | None = None,
    iso_week: int | None = None,
):

    if user["role"] != "ops":
        raise HTTPException(status_code=403, detail="Ops only")

    try:
        cur_year, cur_week = resolve_week(iso_year, iso_week)
        prv_year, prv_week = prev_iso_week(cur_year, cur_week)
        stores = db.query(Store).all()

        store_revenues = (
            db.query(
                Transaction.store_id,
                func.sum(Transaction.total_price).label("revenue"),
                func.count(Transaction.transaction_id).label("txns"),
            )
            .join(Submission, Submission.submission_id == Transaction.submission_id)
            .filter(
                extract("isoyear", Submission.week_start) == cur_year,
                extract("week",    Submission.week_start) == cur_week,
                Submission.status == "active",
            )
            .group_by(Transaction.store_id)
            .all()
        )
        rev_map  = {r.store_id: float(r.revenue) for r in store_revenues}
        txns_map = {r.store_id: int(r.txns)      for r in store_revenues}

        prv_txns_total = (
            db.query(func.count(Transaction.transaction_id))
            .join(Submission, Submission.submission_id == Transaction.submission_id)
            .filter(
                extract("isoyear", Submission.week_start) == prv_year,
                extract("week",    Submission.week_start) == prv_week,
                Submission.status == "active",
            )
            .scalar() or 0
        )
        cur_txns_total = sum(txns_map.values())

        submissions = db.query(Submission).filter(
            extract("isoyear", Submission.week_start) == cur_year,
            extract("week",    Submission.week_start) == cur_week,
            Submission.status == "active",
        ).all()
        sub_map = {s.store_id: s for s in submissions}

        max_revenue = max(
            (rev_map.get(s.store_id, 0) for s in stores), default=1
        ) or 1

        store_stats = []
        for store in stores:
            rev = rev_map.get(store.store_id, 0)
            sub = sub_map.get(store.store_id)
            store_stats.append({
                "store_id":          store.store_id,
                "store_name":        store.store_name,
                "location":          store.location,
                "week_revenue":      rev,
                "week_transactions": txns_map.get(store.store_id, 0),
                "submitted":         sub is not None,
                "submitted_at":      sub.submitted_at.isoformat() if sub and sub.submitted_at else None,
                "pct_of_max":        round((rev / max_revenue) * 100, 1),
            })

        store_stats.sort(key=lambda x: x["week_revenue"], reverse=True)

        top     = store_stats[0] if store_stats else None
        avg_rev = (
            sum(s["week_revenue"] for s in store_stats) / len(store_stats)
        ) if store_stats else 0
        top_vs_avg = (
            round(((top["week_revenue"] - avg_rev) / avg_rev) * 100, 1)
            if top and avg_rev > 0 else None
        )

        pending_stores = [s["store_name"] for s in store_stats if not s["submitted"]]

        return {
            "stores":                 store_stats,
            "top_store_name":         top["store_name"] if top else None,
            "top_store_revenue":      top["week_revenue"] if top else 0,
            "top_store_vs_avg_pct":   top_vs_avg,
            "transactions_delta_pct": pct_change(cur_txns_total, int(prv_txns_total)),
            "pending_stores":         pending_stores,
            "submitted_count":        len(sub_map),
            "total_stores":           len(stores),
            "week_label":             week_label(cur_year, cur_week),
            "iso_year":               cur_year,
            "iso_week":               cur_week,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ops summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load ops summary")


# ── /available-weeks ──────────────────────────────────────
@router.get("/available-weeks")
def get_available_weeks(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    mode: str = "submitted",  # "submitted" = weeks with data | "all" = every week up to now
):

    if user["role"] not in ["ops", "manager"]:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        cur_year, cur_week = get_current_iso_week()

        if mode == "all":
            start_year = cur_year
            start_week = 1
        else:

            query = db.query(Submission).filter(
                Submission.status == "active",
                Submission.week_start.isnot(None),
            )
            if user["role"] == "manager" and user["store_id"]:
                query = query.filter(Submission.store_id == user["store_id"])

            earliest = query.order_by(Submission.week_start.asc()).first()

            if earliest is None:
                return {
                    "weeks": [{
                        "iso_year":   cur_year,
                        "iso_week":   cur_week,
                        "week_label": week_label(cur_year, cur_week) + " (current)",
                    }]
                }

            start_iso  = earliest.week_start.isocalendar()
            start_year = start_iso[0]
            start_week = start_iso[1]

        all_pairs = _all_weeks_between(start_year, start_week, cur_year, cur_week)

        weeks = []
        for i, (y, w) in enumerate(all_pairs):
            label = week_label(y, w)
            if i == 0:
                label += " (current)"
            weeks.append({"iso_year": y, "iso_week": w, "week_label": label})

        return {"weeks": weeks}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Available weeks error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load available weeks")


# ── /top-products ─────────────────────────────────────────
@router.get("/top-products")
def get_top_products(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    iso_year: int | None = None,
    iso_week: int | None = None,
):
    """Top 5 products by revenue for a given week."""
    cur_year, cur_week = resolve_week(iso_year, iso_week)

    try:
        query = (
            db.query(
                Transaction.product_id,
                Product.product_name,
                func.sum(Transaction.total_price).label("total_revenue"),
                func.sum(Transaction.quantity).label("total_units"),
            )
            .join(Product, Product.product_id == Transaction.product_id)
            .join(
                Submission,
                Submission.submission_id == Transaction.submission_id
            )
            .filter(
                extract("isoyear", Submission.week_start) == cur_year,
                extract("week", Submission.week_start) == cur_week,
                Submission.status == "active",
            )
        )

        query = apply_role_filter(query, user, Transaction)

        results = (
            query
            .group_by(Transaction.product_id, Product.product_name)
            .order_by(func.sum(Transaction.total_price).desc())
            .limit(5)
            .all()
        )

        return {
            "data": [
                {
                    "product_id":    row.product_id,
                    "product_name":  row.product_name,
                    "total_revenue": float(row.total_revenue),
                    "total_units":   int(row.total_units),
                }
                for row in results
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Top products error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load top products")


# ── /inventory-alerts ─────────────────────────────────────
@router.get("/inventory-alerts")
def get_inventory_alerts(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    if user["role"] == "manager" and not user["store_id"]:
        raise HTTPException(status_code=403, detail="No store assigned to this account")
    if user["role"] not in ("manager", "ops"):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        query = (
            db.query(
                Inventory.inventory_id,
                Inventory.stock_quantity,
                Inventory.reorder_level,
                Product.product_name,
                Product.category,
                Product.unit_price,
                Store.store_id.label("store_id"),
                Store.store_name.label("store_name"),
                Store.location.label("store_location"),
            )
            .join(Product, Product.product_id == Inventory.product_id)
            .join(Store, Store.store_id == Inventory.store_id)
            .filter(Inventory.stock_quantity <= Inventory.reorder_level)
        )

        all_inventory_query = db.query(func.count(Inventory.inventory_id))

        if user["role"] == "manager":
            query = query.filter(Inventory.store_id == user["store_id"])
            all_inventory_query = all_inventory_query.filter(
                Inventory.store_id == user["store_id"]
            )

        results = query.order_by(
            (Inventory.reorder_level - Inventory.stock_quantity).desc()
        ).all()

        all_inventory = all_inventory_query.scalar() or 0

        return {
            "alerts": [
                {
                    "inventory_id": row.inventory_id,
                    "product_name": row.product_name,
                    "category": row.category,
                    "unit_price": float(row.unit_price),
                    "stock_quantity": row.stock_quantity,
                    "reorder_level": row.reorder_level,
                    "shortfall": row.reorder_level - row.stock_quantity,
                    "store_id": row.store_id,
                    "store_name": row.store_name,
                    "store_location": row.store_location,
                }
                for row in results
            ],
            "total_alerts": len(results),
            "total_products": int(all_inventory),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Inventory alerts error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load inventory alerts")


# ── /profile ──────────────────────────────────────────────
@router.get("/profile")
def get_profile(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    try:
        user_profile = db.query(User).filter(User.id == user["id"]).first()
        if not user_profile:
            raise HTTPException(status_code=404, detail="User not found")

        store_name, store_location = get_store_info(db, user["store_id"])

        return {
            "username": user_profile.username,
            "role": user["role"],
            "store_name": store_name,
            "location": store_location,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile retrieval error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load profile settings")