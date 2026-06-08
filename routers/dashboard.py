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


def apply_store_filter(query, user):
    if user["role"] == "manager":
        if not user["store_id"]:
            raise HTTPException(status_code=403, detail="No store assigned to this account")
        return query.filter(Transaction.store_id == user["store_id"])
    return query


def apply_inventory_store_filter(query, user):
    if user["role"] == "manager":
        if not user["store_id"]:
            raise HTTPException(status_code=403, detail="No store assigned to this account")
        return query.filter(Inventory.store_id == user["store_id"])
    return query


def get_current_iso_week() -> tuple[int, int]:
    """Returns (iso_year, iso_week) for today."""
    today = date.today()
    iso = today.isocalendar()
    return iso[0], iso[1]


def get_week_revenue(db, user, iso_year: int, iso_week: int) -> float:
    """Sum revenue for a specific ISO year+week."""
    query = db.query(func.sum(Transaction.total_price)).filter(
        extract("isoyear", Transaction.transaction_date) == iso_year,
        extract("week", Transaction.transaction_date) == iso_week,
    )
    query = apply_store_filter(query, user)
    return float(query.scalar() or 0)


def get_week_transactions(db, user, iso_year: int, iso_week: int) -> int:
    """Count transactions for a specific ISO year+week."""
    query = db.query(func.count(Transaction.transaction_id)).filter(
        extract("isoyear", Transaction.transaction_date) == iso_year,
        extract("week", Transaction.transaction_date) == iso_week,
    )
    query = apply_store_filter(query, user)
    return int(query.scalar() or 0)


def get_week_avg_basket(db, user, iso_year: int, iso_week: int) -> float:
    """Avg basket for a specific ISO year+week."""
    query = db.query(func.avg(Transaction.total_price)).filter(
        extract("isoyear", Transaction.transaction_date) == iso_year,
        extract("week", Transaction.transaction_date) == iso_week,
    )
    query = apply_store_filter(query, user)
    return float(round(query.scalar() or 0, 2))


def prev_iso_week(iso_year: int, iso_week: int) -> tuple[int, int]:
    """Returns the (iso_year, iso_week) for the week before."""
    # Go back 7 days from a date known to be in iso_year/iso_week
    # Jan 4 is always in ISO week 1 of its year
    jan4 = date(iso_year, 1, 4)
    # Monday of iso_week
    monday = jan4 + timedelta(weeks=iso_week - 1) - timedelta(days=jan4.weekday())
    prev_monday = monday - timedelta(weeks=1)
    iso = prev_monday.isocalendar()
    return iso[0], iso[1]


def pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


def week_label(iso_year: int, iso_week: int) -> str:
    """Human-readable label like 'Week 18 · May 2024'."""
    jan4 = date(iso_year, 1, 4)
    monday = jan4 + timedelta(weeks=iso_week - 1) - timedelta(days=jan4.weekday())
    month_name = monday.strftime("%b %Y")
    return f"Week {iso_week} · {month_name}"

@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    """Securely returns the current user profile."""
    return user


@router.get("/summary")
async def get_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    try:
        # ── All-time aggregates ───────────────────────────
        total_revenue_query = db.query(func.sum(Transaction.total_price))
        total_revenue_query = apply_store_filter(total_revenue_query, user)
        total_revenue = float(total_revenue_query.scalar() or 0)

        total_transactions_query = db.query(func.count(Transaction.transaction_id))
        total_transactions_query = apply_store_filter(total_transactions_query, user)
        total_transactions = int(total_transactions_query.scalar() or 0)

        avg_basket_query = db.query(func.avg(Transaction.total_price))
        avg_basket_query = apply_store_filter(avg_basket_query, user)
        avg_basket = float(round(avg_basket_query.scalar() or 0, 2))

        # ── Stock alerts ──────────────────────────────────
        stock_alert_query = db.query(func.count(Inventory.inventory_id)).filter(
            Inventory.stock_quantity < Inventory.reorder_level
        )
        stock_alert_query = apply_inventory_store_filter(stock_alert_query, user)
        stock_alert_count = int(stock_alert_query.scalar() or 0)

        # ── Current & previous week stats ─────────────────
        cur_year, cur_week = get_current_iso_week()
        prv_year, prv_week = prev_iso_week(cur_year, cur_week)

        cur_revenue = get_week_revenue(db, user, cur_year, cur_week)
        prv_revenue = get_week_revenue(db, user, prv_year, prv_week)

        cur_transactions = get_week_transactions(db, user, cur_year, cur_week)
        prv_transactions = get_week_transactions(db, user, prv_year, prv_week)

        cur_avg_basket = get_week_avg_basket(db, user, cur_year, cur_week)
        prv_avg_basket = get_week_avg_basket(db, user, prv_year, prv_week)

        # ── Week submitted check ──────────────────────────
        week_submitted = False
        if user["role"] == "manager" and user["store_id"]:
            submission = db.query(Submission).filter(
                Submission.store_id == user["store_id"],
                extract("isoyear", Submission.week_start) == cur_year,
                extract("week", Submission.week_start) == cur_week,
            ).first()
            week_submitted = submission is not None

        # ── User profile & store ──────────────────────────
        user_profile = db.query(User).filter(User.id == user["id"]).first()
        user_name = user_profile.username if user_profile else None

        store_name = None
        store_location = None
        if user["store_id"]:
            store = db.query(Store).filter(Store.store_id == user["store_id"]).first()
            if store:
                store_name = store.store_name
                store_location = store.location

        return {
            "total_revenue": total_revenue,
            "total_transactions": total_transactions,
            "avg_basket": avg_basket,
            "stock_alert_count": stock_alert_count,

            # Current week metrics
            "week_number": cur_week,
            "week_label": week_label(cur_year, cur_week),
            "week_submitted": week_submitted,
            "week_revenue": cur_revenue,
            "week_transactions": cur_transactions,
            "week_avg_basket": cur_avg_basket,

            # Week-on-week deltas (null if no previous data)
            "revenue_delta_pct": pct_change(cur_revenue, prv_revenue),
            "transactions_delta_pct": pct_change(cur_transactions, prv_transactions),
            "avg_basket_delta_pct": pct_change(cur_avg_basket, prv_avg_basket),

            "store_id": user["store_id"],
            "store_name": store_name,
            "store_location": store_location,
            "user_name": user_name,
            "role": user["role"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard summary")


@router.get("/revenue-trend")
async def get_revenue_trend(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Returns the last 8 ISO weeks of revenue, each labelled W{n}."""
    try:
        iso_year = extract("isoyear", Transaction.transaction_date).label("iso_year")
        iso_week = extract("week", Transaction.transaction_date).label("iso_week")

        query = db.query(
            iso_year,
            iso_week,
            func.sum(Transaction.total_price).label("revenue"),
        )
        query = apply_store_filter(query, user)

        results = (
            query
            .group_by(iso_year, iso_week)
            .order_by(iso_year, iso_week)
            .all()
        )

        results = results[-8:]

        return {
            "data": [
                {
                    "date": f"W{int(row.iso_week)}",
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


@router.get("/ops-summary")
async def get_ops_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):

    if user["role"] != "ops":
        raise HTTPException(status_code=403, detail="Ops only")

    try:
        cur_year, cur_week = get_current_iso_week()
        prv_year, prv_week = prev_iso_week(cur_year, cur_week)

        # ── All stores ────────────────────────────────────
        stores = db.query(Store).all()

        # ── Per-store week revenue ────────────────────────
        store_revenues = (
            db.query(
                Transaction.store_id,
                func.sum(Transaction.total_price).label("revenue"),
                func.count(Transaction.transaction_id).label("txns"),
            )
            .filter(
                extract("isoyear", Transaction.transaction_date) == cur_year,
                extract("week",    Transaction.transaction_date) == cur_week,
            )
            .group_by(Transaction.store_id)
            .all()
        )
        rev_map  = {r.store_id: float(r.revenue) for r in store_revenues}
        txns_map = {r.store_id: int(r.txns)     for r in store_revenues}

        # Previous week total transactions for delta
        prv_txns_total = (
            db.query(func.count(Transaction.transaction_id))
            .filter(
                extract("isoyear", Transaction.transaction_date) == prv_year,
                extract("week",    Transaction.transaction_date) == prv_week,
            )
            .scalar() or 0
        )
        cur_txns_total = sum(txns_map.values())

        # ── Submissions this week ─────────────────────────
        submissions = db.query(Submission).filter(
            extract("isoyear", Submission.week_start) == cur_year,
            extract("week",    Submission.week_start) == cur_week,
        ).all()
        sub_map = {s.store_id: s for s in submissions}

        # ── Build per-store list ──────────────────────────
        max_revenue = max((rev_map.get(s.store_id, 0) for s in stores), default=1) or 1

        store_stats = []
        for store in stores:
            rev = rev_map.get(store.store_id, 0)
            sub = sub_map.get(store.store_id)
            store_stats.append({
                "store_id":      store.store_id,
                "store_name":    store.store_name,
                "location":      store.location,
                "week_revenue":  rev,
                "week_transactions": txns_map.get(store.store_id, 0),
                "submitted":     sub is not None,
                "submitted_at":  sub.submitted_at.isoformat() if sub and sub.submitted_at else None,
                "pct_of_max":    round((rev / max_revenue) * 100, 1),
            })

        # Sort by revenue desc
        store_stats.sort(key=lambda x: x["week_revenue"], reverse=True)

        # ── Top store ─────────────────────────────────────
        top = store_stats[0] if store_stats else None
        avg_rev = (sum(s["week_revenue"] for s in store_stats) / len(store_stats)) if store_stats else 0
        top_vs_avg = round(((top["week_revenue"] - avg_rev) / avg_rev) * 100, 1) if top and avg_rev > 0 else None

        # ── Pending stores ────────────────────────────────
        pending_stores = [s["store_name"] for s in store_stats if not s["submitted"]]

        return {
            "stores":                store_stats,
            "top_store_name":        top["store_name"] if top else None,
            "top_store_revenue":     top["week_revenue"] if top else 0,
            "top_store_vs_avg_pct":  top_vs_avg,
            "transactions_delta_pct": pct_change(cur_txns_total, int(prv_txns_total)),
            "pending_stores":        pending_stores,
            "submitted_count":       len(sub_map),
            "total_stores":          len(stores),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ops summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load ops summary")


@router.get("/top-products")
async def get_top_products(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Returns top 5 products by revenue with real product names."""
    try:
        query = db.query(
            Transaction.product_id,
            Product.product_name,
            func.sum(Transaction.total_price).label("total_revenue"),
            func.sum(Transaction.quantity).label("total_units"),
        ).join(Product, Product.product_id == Transaction.product_id)

        query = apply_store_filter(query, user)

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
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "total_revenue": float(row.total_revenue),
                    "total_units": int(row.total_units),
                }
                for row in results
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Top products error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load top products")