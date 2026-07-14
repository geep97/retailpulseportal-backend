import io
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import extract
from database import get_db
from models import Submission, Transaction, Inventory, IntegrityLog, Product
from routers.auth import role_required, get_current_user
import logging
from datetime import date

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Data Ingestion Pipeline"])


REQUIRED_COLUMNS = {
    "transaction_id", "transaction_date", "product_name",
    "category", "quantity", "unit_price", "payment_method"
}

OPTIONAL_COLUMNS = {"total_revenue", "customer_id"}

VALID_CATEGORIES = {
    "Electronics", "Grocery", "Clothing",
    "Household", "Health & Beauty"
}

VALID_PAYMENT_METHODS = {"Cash", "Mobile Money", "Bank Card", "Credit"}



def align_schema(df: pd.DataFrame) -> pd.DataFrame:

    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")


    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


    if "total_revenue" not in df.columns:
        df["total_revenue"] = None
    if "customer_id" not in df.columns:
        df["customer_id"] = ""


    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")


    for col in ["product_name", "category", "payment_method"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df



def exclude_anomalies(df: pd.DataFrame):
    excluded = []
    clean_mask = pd.Series([True] * len(df), index=df.index)

    # Condition A — negative or zero unit price
    bad_price = df["unit_price"].apply(
        lambda x: not isinstance(x, (int, float)) or x <= 0
    )
    # Condition B — zero or negative quantity
    bad_qty = df["quantity"].apply(
        lambda x: not isinstance(x, (int, float)) or x <= 0
    )
    # Condition C — unparseable date
    bad_date = df["transaction_date"].isna() | (df["transaction_date"] == "NaT")

    for idx in df[bad_price].index:
        excluded.append({
            "row": idx + 2,  # +2 for header row and 0-index
            "reason": "Unit price is zero or negative"
        })

    for idx in df[bad_qty & ~bad_price].index:
        excluded.append({
            "row": idx + 2,
            "reason": "Quantity is zero or negative"
        })

    for idx in df[bad_date & ~bad_price & ~bad_qty].index:
        excluded.append({
            "row": idx + 2,
            "reason": "Transaction date could not be parsed"
        })

    clean_mask = ~(bad_price | bad_qty | bad_date)
    clean_df = df[clean_mask].copy()

    return clean_df, excluded


# ── STEP 3: AUTO-FIX ENGINE ──────────────────────────────────
def auto_fix(df: pd.DataFrame):
    fixes = []

    # Fix A — recalculate missing total_revenue
    missing_total = df["total_revenue"].isna() | (df["total_revenue"] == "")
    if missing_total.any():
        df.loc[missing_total, "total_revenue"] = (
            df.loc[missing_total, "quantity"] *
            df.loc[missing_total, "unit_price"]
        ).round(2)
        fixes.append(
            f"{missing_total.sum()} rows had missing revenue totals — "
            f"recalculated from quantity × unit price"
        )

    # Fix B — empty payment method
    missing_payment = df["payment_method"].isna() | (df["payment_method"] == "")
    if missing_payment.any():
        df.loc[missing_payment, "payment_method"] = "Unknown"
        fixes.append(
            f"{missing_payment.sum()} rows had no payment method — "
            f"recorded as Unknown"
        )

    # Fix C — empty product name
    missing_product = df["product_name"].isna() | (df["product_name"] == "")
    if missing_product.any():
        df.loc[missing_product, "product_name"] = "Unknown"
        fixes.append(
            f"{missing_product.sum()} rows had no product name — "
            f"recorded as Unknown"
        )

    # Convert total_revenue to float
    df["total_revenue"] = pd.to_numeric(
        df["total_revenue"], errors="coerce"
    ).fillna(0.0)

    return df, fixes


# ── STEP 4: DUPLICATE WEEK CHECK ─────────────────────────────
def check_duplicate_submission(
    db: Session,
    store_id: int,
    iso_year: int,
    iso_week: int
):
    existing = db.query(Submission).filter(
        Submission.store_id == store_id,
        extract("isoyear", Submission.week_start) == iso_year,
        extract("week", Submission.week_start) == iso_week,
        Submission.status == "active"
    ).first()
    return existing



# ── PRODUCT RESOLVER ─────────────────────────────────────────
def resolve_product_id(db: Session, product_name: str, unit_price: float, category: str) -> int:

    product = db.query(Product).filter(
        Product.product_name == product_name
    ).first()
    if product:
        return product.product_id

    new_product = Product(
        product_name=product_name,
        unit_price=unit_price,
        category=category or "Uncategorised",
    )
    db.add(new_product)
    db.flush()
    return new_product.product_id


# ── STEP 5: ETL WRITE (ATOMIC) ────────────────────────────────
def write_to_database(
    db: Session,
    store_id: int,
    iso_year: int,
    iso_week: int,
    submitted_by: str,
    filename: str,
    df: pd.DataFrame,
    excluded: list,
    fixes: list,
    replace_submission_id: int = None
):
    try:
        # If replacing — mark old submission inactive
        if replace_submission_id:
            old = db.query(Submission).filter(
                Submission.submission_id == replace_submission_id
            ).first()
            if old:
                old.status = "inactive"
                db.flush()

        # Calculate week boundaries
        from datetime import timedelta
        jan4 = date(iso_year, 1, 4)
        monday = jan4 + timedelta(
            weeks=iso_week - 1
        ) - timedelta(days=jan4.weekday())
        sunday = monday + timedelta(days=6)

        # Create submission record
        submission = Submission(
            store_id=store_id,
            week_label=f"Week {iso_week} · {monday.strftime('%b %Y')}",
            period_year=iso_year,
            period_month=monday.month,
            week_start=monday,
            week_end=sunday,
            filename=filename,
            status="active",
            submitted_by=submitted_by,
        )
        db.add(submission)
        db.flush()  # get submission_id without committing

        # Write transaction rows
        for _, row in df.iterrows():
            product_id = resolve_product_id(
                db,
                product_name = str(row["product_name"]),
                unit_price   = float(row["unit_price"]),
                category     = str(row.get("category", "")),
            )
            txn = Transaction(
                submission_id    = submission.submission_id,
                store_id         = store_id,
                product_id       = product_id,
                customer_id      = int(row["customer_id"]) if str(row.get("customer_id", "")).isdigit() else None,
                transaction_date = row["transaction_date"],
                quantity         = int(float(row["quantity"])),
                unit_price       = float(row["unit_price"]),
                total_price      = float(row["total_revenue"]),
                payment_method   = str(row["payment_method"]).strip() if str(row["payment_method"]).strip().lower() not in ("", "nan", "none") else "Unknown",
            )
            db.add(txn)

        # Write integrity log
        exclusion_notes = "; ".join(
            [f"Row {e['row']}: {e['reason']}" for e in excluded]
        ) if excluded else "None"

        fix_notes = "; ".join(fixes) if fixes else "None"

        log = IntegrityLog(
            submission_id=submission.submission_id,
            total_received=len(df) + len(excluded),
            total_included=len(df),
            total_excluded=len(excluded),
            total_fixed=len(fixes),
            exclusion_notes=exclusion_notes,
            fix_notes=fix_notes
        )
        db.add(log)

        # COMMIT everything atomically
        db.commit()

        return submission.submission_id

    except Exception as e:
        db.rollback()  # ROLLBACK — nothing written
        raise e


# ── MAIN UPLOAD ENDPOINT ─────────────────────────────────────
@router.post("/upload")
def upload_weekly_ledger(
        iso_year: int = Form(...),
        iso_week: int = Form(...),
        confirm_replace: bool = Form(default=False),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):

    if user["role"] != "manager":
        raise HTTPException(
            status_code=403,
            detail="Only store managers can upload files."
        )


    store_id = user["store_id"]
    if not store_id:
        raise HTTPException(
            status_code=403,
            detail="No store assigned to your account."
        )

    # File format check
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are accepted. Please export your data as CSV."
        )

    try:
        contents = file.file.read()

        # ── STEP 1: Try to read the file ──────────────────────
        try:
            df = pd.read_csv(io.BytesIO(contents))
        except Exception:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Your file could not be read. Please check that it is a "
                    "valid CSV export and try again."
                )
            )

        total_received = len(df)

        # ── STEP 2: Schema alignment ──────────────────────────
        try:
            df = align_schema(df)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=f"File structure problem: {str(e)}"
            )

        # ── STEP 3: Anomaly exclusion ─────────────────────────
        df, excluded = exclude_anomalies(df)

        # ── STEP 4: Auto-fix ──────────────────────────────────
        df, fixes = auto_fix(df)

        # ── STEP 5: Duplicate check ───────────────────────────
        existing = check_duplicate_submission(
            db, store_id, iso_year, iso_week
        )

        if existing and not confirm_replace:
            return {
                "status": "duplicate_warning",
                "message": (
                    f"Your store already has an active submission for "
                    f"Week {iso_week}. Do you want to replace it?"
                ),
                "existing_submission_id": existing.submission_id,
                "total_received": total_received,
            }

        # ── STEP 6: ETL write (atomic) ────────────────────────
        replace_id = existing.submission_id if existing else None
        submission_id = write_to_database(
            db=db,
            store_id=store_id,
            iso_year=iso_year,
            iso_week=iso_week,
            submitted_by=user["id"],
            filename=file.filename,
            df=df,
            excluded=excluded,
            fixes=fixes,
            replace_submission_id=replace_id
        )

        # ── STEP 7: Return integrity summary ──────────────────
        return {
            "status": "success",
            "submission_id": submission_id,
            "week_label": f"Week {iso_week}",
            "total_received": total_received,
            "total_included": len(df),
            "total_excluded": len(excluded),
            "total_fixed": len(fixes),
            "exclusion_details": excluded if excluded else [],
            "fix_details": fixes if fixes else [],
            "message": (
                f"Your file was accepted. "
                f"{len(df)} transactions recorded for Week {iso_week}."
            ) if not excluded else (
                f"Your file was accepted with notes. "
                f"{len(df)} transactions recorded, "
                f"{len(excluded)} excluded. See details below."
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error store {store_id} week {iso_week}: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                "Something went wrong processing your file. "
                "Please try again or contact your system administrator."
            )
        )


# ── UPLOAD HISTORY ENDPOINT ───────────────────────────────────
@router.get("/upload/history")
def get_upload_history(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    store_id = user["store_id"]
    if not store_id:
        raise HTTPException(status_code=403, detail="No store assigned to your account.")

    from sqlalchemy import func as sqlfunc
    from models import Transaction as Txn

    rows = (
        db.query(
            Submission,
            IntegrityLog.total_included,
            IntegrityLog.total_excluded,
            IntegrityLog.total_fixed,
            sqlfunc.coalesce(sqlfunc.sum(Txn.total_price), 0).label("total_revenue"),
        )
        .outerjoin(IntegrityLog, IntegrityLog.submission_id == Submission.submission_id)
        .outerjoin(Txn, Txn.submission_id == Submission.submission_id)
        .filter(Submission.store_id == store_id, Submission.status == "active")
        .group_by(Submission.submission_id, IntegrityLog.total_included,
                  IntegrityLog.total_excluded, IntegrityLog.total_fixed)
        .order_by(Submission.submitted_at.desc())
        .limit(20)
        .all()
    )

    return {
        "history": [
            {
                "submission_id": s.submission_id,
                "week_label":    s.week_label,
                "week_start":    s.week_start.isoformat() if s.week_start else None,
                "submitted_at":  s.submitted_at.isoformat() if s.submitted_at else None,
                "filename":      s.filename,
                "status":        s.status,
                "total_included": total_included or 0,
                "total_excluded": total_excluded or 0,
                "total_fixed":    total_fixed    or 0,
                "total_revenue":  float(total_revenue or 0),
            }
            for s, total_included, total_excluded, total_fixed, total_revenue in rows
        ]
    }