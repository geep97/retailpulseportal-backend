# RetailPulse Portal — Code Review & Engineering Mentorship Report

**Reviewed against:** Phase 1 Requirements (RPG-2024-DE-002) · Current codebase state
**Audience:** Junior Data Engineer (Trainee)
**Date:** 05 June 2026

---

## How to Read This Review

Every finding has a **severity label**:

| Label | Meaning |
|---|---|
| `[CRITICAL]` | A real security vulnerability or data-loss risk. Fix before any user touches this. |
| `[HIGH]` | Broken functionality or a pattern that will cause serious problems at scale. |
| `[MEDIUM]` | Won't break things today but is wrong for production and will hurt you later. |
| `[LOW]` | Code quality, clarity, and craft issues. The kind of thing senior engineers notice in a PR review. |
| `[ARCHITECTURE]` | Design-level gaps between what was built and what was specified. |

The goal is not to list faults — it is to build the right instincts. After each finding you will see **Why this matters** and **What to do**, because understanding the reason is more important than the fix.

---

## Section 1 — What Was Done Well

Before anything critical, here is what deserves recognition:

- **The login page is clean, accessible, and well-structured.** The use of `htmlFor`/`id` pairing on form fields, `autoComplete` attributes, and `aria`-friendly `role="note"` on the notice box shows attentiveness to HTML best practices. This is better than most junior work.

- **The RBAC middleware pattern (`role_required`) is architecturally sound.** Using a dependency factory that returns a `Depends(checker)` is the idiomatic FastAPI way to handle role-based protection. Good instinct.

- **The seeding script (`test_db.py`) is well-structured.** Chunked upserts, graceful handling of unmatched products, and clear print logging show thoughtful execution logic.

- **The migration file's `downgrade()` function is more detailed than `upgrade()`.** The fact that you preserved the full schema in downgrade — column types, constraints, foreign keys — shows you understood what Alembic migrations are for. That detail matters.

- **TypeScript is used correctly in the frontend.** The `Feature` interface, typed state, and typed event handler (`React.FormEvent<HTMLFormElement>`) are all correct. You're using TypeScript like TypeScript, not like JavaScript with type annotations bolted on.

---

## Section 2 — Critical Security Issues

### `[CRITICAL]` Tokens are stored in `localStorage` — XSS vulnerability

**File:** `frontend/retail-pulse-web-app/src/pages/LoginPage.tsx:42`

```typescript
localStorage.setItem('access_token', data.access_token);
```

**Why this matters:** `localStorage` is readable by any JavaScript running on your page. If an attacker injects a single script tag through a future XSS vulnerability anywhere in your app, they silently steal every user's token. For a system with `role: "ops"` users who can create other users, this is a complete account takeover.

**What to do:** The production pattern for JWTs in browser applications is `httpOnly` cookies. These are set by the server and cannot be read by JavaScript at all. The browser sends them automatically on every request. Restructure your login endpoint to set a cookie instead of returning the token in the JSON body:

```python
# backend: set an httpOnly cookie instead of returning the token
from fastapi import Response

@router.post("/login")
async def login(credentials: LoginRequest, response: Response, db: Session = Depends(get_db)):
    # ... auth logic ...
    response.set_cookie(
        key="access_token",
        value=session.access_token,
        httponly=True,
        secure=True,      # HTTPS only in production
        samesite="lax",
        max_age=3600
    )
    return {"role": user_profile.role}
```

> **The rule:** Never store authentication credentials where JavaScript can read them.

---

### `[CRITICAL]` Login errors expose internal exception messages

**File:** `backend/routers/auth.py:91`

```python
raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")
```

**Why this matters:** `str(e)` can contain Supabase SDK internals, database error messages, network details, or stack fragments. You are handing attackers a detailed map of your system internals. A response of `"Login failed: Invalid API key"` or `"Login failed: connection to server at '...' failed"` tells an attacker far more than they should know.

**What to do:** User-facing error messages must be generic. Internal errors must be logged server-side only:

```python
import logging
logger = logging.getLogger(__name__)

except Exception as e:
    logger.error(f"Login error for {credentials.email}: {e}")
    raise HTTPException(status_code=401, detail="Invalid email or password.")
```

> **The rule:** Log the truth internally, show nothing useful externally.

---

### `[CRITICAL]` The dashboard route does not exist

**Files:** `frontend/retail-pulse-web-app/src/App.tsx` and `LoginPage.tsx:48`

```typescript
navigate('/dashboard');  // LoginPage.tsx — navigates here on success

// App.tsx — only this route is registered:
<Route path="/" element={<LoginPage />} />
```

**Why this matters:** Logging in successfully redirects the user to a blank page (or a 404-equivalent). The system is broken for every user who successfully authenticates. This is the most visible bug in the project.

**What to do:** Either add a placeholder `DashboardPage` component and register it as a route, or redirect back to `/` if the dashboard isn't built yet. What you cannot do is navigate to a route that doesn't exist. Before merging any frontend change, always verify that every `navigate()` call points to a registered route.

---

### `[HIGH]` No route protection — authentication is not enforced

**File:** `frontend/retail-pulse-web-app/src/App.tsx`

**Why this matters:** Any user can type `/dashboard` in their browser and reach it (once it exists) without being authenticated. A system with per-branch data isolation — a non-negotiable requirement per Section 3 of the PRD — that doesn't enforce authentication on protected routes is not a secure system.

**What to do:** Build a `ProtectedRoute` wrapper component. This is standard React Router practice:

```typescript
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('access_token');
  if (!token) return <Navigate to="/" replace />;
  return <>{children}</>;
}

// In App.tsx:
<Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
```

> Note: Once you switch to `httpOnly` cookies, the guard checks an auth state context rather than `localStorage`.

---

## Section 3 — High Severity Issues

### `[HIGH]` The upload endpoint is a skeleton — the core requirement is unimplemented

**File:** `backend/routers/ingestion.py`

```python
df = pd.read_csv(io.BytesIO(contents))
return {"success": True, "message": f"Pipeline executed for {user.email}"}
```

**Why this matters:** The entire purpose of this system — per Sections 5 and 6 of the PRD — is to validate uploaded data, run integrity checks, apply automatic fixes, log exclusions, and store the processed results. The upload endpoint reads the CSV and **discards it**. It returns `"success": True` regardless of what was in the file. This will mislead a manager into thinking their data was processed when it was not.

**What to do:** This is Sprint 2's core deliverable. The function signature and route exist — that is the right foundation. The body needs to be built: validate column presence, check for negative prices and zero quantities, apply auto-fixes for missing totals, write to the database, and return a structured integrity summary.

> **The lesson:** Returning a success response from an incomplete function is more dangerous than returning an error. A fake success hides the gap. If a feature is not yet implemented, either raise `HTTP 501 Not Implemented` or don't register the route. **Never lie to the caller.**

---

### `[HIGH]` `id` and `auth_provider_id` are redundant — the data model is self-contradictory

**Files:** `backend/models.py` and `backend/routers/auth.py:117–129`

```python
# create_user — both id and auth_provider_id are set to the same value:
new_profile = User(id=auth_id, username=user_data.username, role=user_data.role, auth_provider_id=auth_id)

# But get_current_user filters by auth_provider_id:
profile = db.query(User).filter(User.auth_provider_id == supabase_user.id).first()

# While create_user looks up by id:
profile = db.query(User).filter(User.id == auth_id).first()
```

**Why this matters:** You have two columns pointing to the same value, and different parts of the code use different columns to do the same lookup. This is a contradiction in the data model. It will cause a hard-to-debug failure if either value is ever updated independently, and it signals unclear thinking about what each column means.

**What to do:** Make a decision. Since Supabase generates the UUID and you're storing it as the profile `id`, you only need one column. Remove `auth_provider_id` from the model and use `User.id` as the foreign key to Supabase's `auth.users`. If there was a reason to have both (e.g., supporting multiple auth providers in the future), document that reason explicitly.

---

### `[HIGH]` The `models.py` file is misleading and non-functional

**File:** `backend/models.py`

```python
# What the model says:
class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_id = Column(Integer, primary_key=True)  # just a PK — nothing else

class Product(Base):
    __tablename__ = "product"
    product_id = Column(Integer, primary_key=True)
    product_name = Column(String, nullable=False)
    unit_price = Column(Integer, nullable=False)   # ← Integer, not NUMERIC
    category = Column(String)
```

```python
# What the actual database has (from the migration's downgrade()):
# audit_log: user_id, store_id, event_type, event_detail, occurred_at, severity (with CHECK constraint)
# product: product_name, category, unit_price as NUMERIC(10, 2)
```

**Why this matters:** The SQLAlchemy models are the code's contract with the database. They allow you to write typed queries, validate data at the ORM layer, and prevent mismatches between your code and the schema. When models are stripped to just a primary key, the ORM provides zero protection. You could write `Product(product_name="x")` and the model won't stop you from creating a record missing the category field the schema requires.

**What to do:** Every model must match its actual database schema, column for column, type for type, constraint for constraint. After you fix the models, Alembic migrations should be **generated from the models** — not written independently of them.

---

### `[HIGH]` Alembic `upgrade()` drops all tables — this is a data-loss trap

**File:** `backend/alembic/versions/8807e577f92f_add_auth_provider.py:24–31`

```python
def upgrade() -> None:
    op.drop_table('submissions')
    op.drop_table('transactions')
    op.drop_table('product')
    op.drop_table('stores')
    op.drop_table('audit_log')
    op.drop_table('customers')
    op.drop_table('inventory')
    op.drop_table('integrity_log')
    # ... then alters the profiles table
```

**Why this matters:** If this migration is run against a production database that contains customer records, transaction history, and inventory data, **all of it is permanently deleted.** The entire Phase 0 baseline that the PRD says "must already be loaded when the system first starts" would be wiped. This is an irreversible operation.

**What to do:** Migrations that add a column or change a column type must never drop unrelated tables. The correct approach for `add_auth_provider` is to only alter the `profiles` table. Always ask yourself before running a migration: *"If this runs in production, what data disappears?"*

---

### `[HIGH]` Error handling masks real failures in `get_current_user`

**File:** `backend/routers/auth.py:47–51`

```python
except HTTPException:
    raise
except Exception as e:
    raise HTTPException(status_code=401, detail="Could not validate credentials")
```

**Why this matters:** A database connection failure, a memory error, or a programming bug in the function body will all be silently converted to a `401 Unauthorized`. Your monitoring and logging will show a wave of 401s and you will have no idea that the real cause is a dropped database connection. This is called **swallowing errors**.

**What to do:** Catch specific exceptions. Supabase SDK auth errors → `401`. Database query errors → `500`. Programming errors should propagate and crash loudly in development so you find them immediately. Only catch what you know how to handle.

---

## Section 4 — Medium Severity Issues

### `[MEDIUM]` Hardcoded `localhost` URL in the frontend

**File:** `frontend/retail-pulse-web-app/src/pages/LoginPage.tsx:32`

```typescript
const response = await fetch('http://localhost:8000/login', {
```

**Why this matters:** This URL is different in every environment — local development, staging, and production all have different backend addresses. When you deploy this, it will fail immediately and require a code change. This couples your code to your local machine.

**What to do:** Use Vite's built-in environment variable system:

```bash
# .env.local (not committed to git)
VITE_API_URL=http://localhost:8000

# .env.production
VITE_API_URL=https://api.retailpulse.yourhost.com
```

```typescript
// LoginPage.tsx
const response = await fetch(`${import.meta.env.VITE_API_URL}/login`, {
```

Add `.env.local` to `.gitignore`. Commit `.env.example` with placeholder values. This is standard practice for every production application.

---

### `[MEDIUM]` Two conflicting data access patterns with no clear ownership

**Files:** `backend/database.py`, `backend/routers/auth.py`, `backend/test_db.py`

The codebase uses **SQLAlchemy ORM** for `profiles` (via `db.query(User)`) and the **Supabase Python SDK** for everything else (`supabase.table("customers").upsert(...)`). These are two different database clients talking to the same underlying PostgreSQL instance.

**Why this matters:** Two clients means two connection pools, two transaction scopes, and two potential sources of inconsistency. A SQLAlchemy transaction and a Supabase SDK call cannot be part of the same atomic operation. If you write to `transactions` via the Supabase SDK and update `submissions` via SQLAlchemy and one fails, the other has already committed — you now have inconsistent data.

**What to do:** Pick one pattern and commit to it for all data access:
- **SQLAlchemy for everything** — full ORM, proper models, atomic transactions
- **Supabase SDK for everything** — simpler for this use case, built-in RLS support

Mixing them is not a third option — it is a problem waiting to happen.

---

### `[MEDIUM]` `setTimeout` for navigation is an anti-pattern

**File:** `frontend/retail-pulse-web-app/src/pages/LoginPage.tsx:46–50`

```typescript
setTimeout(() => {
  navigate('/dashboard');
}, 1000);
```

**Why this matters:** If the component unmounts before the timeout fires (e.g., the user clicks elsewhere), you trigger a state update on an unmounted component — a React memory leak that produces console warnings. The timeout also makes the app feel slow for no functional reason.

**What to do:** Navigate immediately. If you need to pass a success message across routes, use React Router's `state` prop:

```typescript
navigate('/dashboard', { state: { fromLogin: true } });
```

---

### `[MEDIUM]` File extension check is bypassable

**File:** `backend/routers/ingestion.py:15`

```python
if not file.filename.endswith('.csv'):
    raise HTTPException(status_code=400, detail="Only CSV allowed.")
```

**Why this matters:** Anyone can rename `malware.exe` to `malware.csv` and this check passes. Filename extensions are metadata provided by the user and **cannot be trusted**.

**What to do:** Validate the actual MIME type and verify the file can be parsed as CSV:

```python
if file.content_type not in ("text/csv", "application/csv", "text/plain"):
    raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

try:
    df = pd.read_csv(io.BytesIO(contents))
except Exception:
    raise HTTPException(status_code=400, detail="Your file could not be read. Please check that it is a valid CSV export and try again.")
```

This also satisfies Acceptance Criterion #12 in the PRD.

---

### `[MEDIUM]` `database.py` crashes at startup if environment variables are missing

**File:** `backend/database.py:16–19`

```python
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
admin_supabase: Client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)
```

**Why this matters:** These lines execute at module import time. If `SUPABASE_URL` is `None` (because `.env` wasn't loaded or the key is missing), the application crashes with a cryptic SDK error before FastAPI can even start, giving no hint about which environment variable is missing.

**What to do:**

```python
if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError(
        "SUPABASE_URL and SUPABASE_KEY must be set. "
        "Copy .env.example to .env and fill in the values."
    )
```

> **The rule:** Fail fast with a clear message — never fail late with a cryptic one.

---

### `[MEDIUM]` `unit_price` is stored as `Integer` — money is never an integer

**File:** `backend/models.py:22`

```python
unit_price = Column(Integer, nullable=False)  # ← wrong type
```

The migration's `downgrade()` reveals the actual column type:

```python
sa.Column('unit_price', sa.NUMERIC(precision=10, scale=2), ...)
```

**Why this matters:** Storing prices as integers silently truncates decimal values. A product priced at GHS 149.99 stored as `Integer` becomes GHS 149. Every revenue calculation in the system will be wrong. This is a data integrity issue with direct business impact.

**What to do:** Use `Numeric(precision=10, scale=2)` for every money column. **Money is never an integer.** This is universal.

---

### `[MEDIUM]` `iterrows()` is a known pandas anti-pattern

**File:** `backend/test_db.py:75`

```python
for _, row in inv_df.iterrows():
```

**Why this matters:** `iterrows()` converts each row to a Python object and iterates one at a time. For 250 records it is fine. For 100,000 rows it is a serious performance problem. Getting into the habit now will cost you later.

**What to do:** Use `df.to_dict('records')` for building payloads:

```python
records = inv_df.to_dict('records')
inv_payloads = [
    {
        "store_id": store_map[r["store_name"]],
        "product_id": product_map[r["product_name"]],
        "stock_quantity": int(r["stock_qty"]),
        "reorder_level": int(r["reorder_level"]),
        "supplier": r.get("supplier", "Main Retail Vendor Distribution Hub"),
    }
    for r in records
    if r["product_name"] in product_map
]
```

---

## Section 5 — Low Severity / Code Craft Issues

### `[LOW]` Inline comments narrate what the code already says

**File:** `backend/routers/auth.py`

```python
# 1. Authenticate with Supabase
response = supabase.auth.sign_in_with_password(...)

# 2. Extract Auth ID
auth_id = str(response.user.id)

# UPDATE: Fetch local profile to get user role
user_profile = db.query(User).filter(User.auth_provider_id == auth_id).first()
```

**Why this matters:** Comments that restate the code add noise and become stale when the code changes. The `# UPDATE:` prefix is a git commit message, not a code comment — it belongs in the commit history, not in the source file.

**What to do:** Delete comments that restate the code. Write comments only when the **WHY** is non-obvious: a hidden constraint, a workaround for a specific bug, a business rule that would surprise a reader.

---

### `[LOW]` `test_db.py` is named like a test file but is a seeding script

**File:** `backend/test_db.py`

**Why this matters:** Any engineer who joins this project and sees `test_db.py` will expect unit tests. They will try to run it with pytest. When it executes real database writes, it will confuse or break things. Misleading names waste time.

**What to do:** Rename it to `seed_data.py` or `scripts/seed_operational_data.py`. Put seeding scripts in a `scripts/` directory separate from application code.

---

### `[LOW]` `App.css` contains default Vite template boilerplate

**File:** `frontend/retail-pulse-web-app/src/App.css`

This file still has the default Vite template styles (`.card`, `#root`, counter button, etc.) from `npm create vite@latest`. None of it is used by the app.

**What to do:** Delete the file contents or the file entirely. Unused code is a maintenance burden — it will confuse the next person who reads it.

---

### `[LOW]` Duplicate `package.json` — confusing project structure

**Files:** `frontend/package.json` and `frontend/retail-pulse-web-app/package.json`

The outer `frontend/package.json` contains only `react-router-dom` and serves no clear purpose. The real app lives inside `retail-pulse-web-app/`.

**What to do:** Remove `frontend/package.json`. Consider flattening the structure so `frontend/` is the Vite project root directly, rather than nesting it inside a subdirectory.

---

### `[LOW]` `.signin-btn:disabled` has no visual state

**File:** `frontend/retail-pulse-web-app/src/pages/LoginPage.css`

The `isLoading` state disables the button and changes its text to `"Signing in..."`, but there is no CSS rule for `.signin-btn:disabled`. The button looks identical to its enabled state, giving the user no visual feedback that something is happening.

**What to do:**

```css
.signin-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
```

---

## Section 6 — Architecture Gaps vs. Requirements

This section maps what the PRD requires against what exists. This is not a criticism of pace — it is an audit of clarity so you know exactly where you stand.

| Requirement (PRD) | Status | Gap |
|---|---|---|
| Sprint 1: Login screen | ✅ Built | — |
| Sprint 1: Two user roles with RBAC | ✅ Built | `store_id` is stored in profiles but **never used to filter queries** — data isolation is not enforced |
| Sprint 1: 2023 baseline data loaded | ✅ Seeder built | Seeder is a standalone script, not wired into the setup process |
| Sprint 1: Basic post-login home screen | ❌ Missing | `/dashboard` route does not exist |
| Sprint 2: File upload UI | ❌ Missing | No week selector, no file picker in the frontend |
| Sprint 2: Integrity check engine | ❌ Missing | Upload endpoint reads CSV, discards it, returns fake success |
| Sprint 2: Integrity summary screen | ❌ Missing | — |
| Sprint 2: Duplicate submission warning | ❌ Missing | — |
| Sprint 3 & 4: All dashboards | ❌ Missing | No dashboard pages exist |

### The most important missing piece: data isolation at the query level

The PRD states in bold: *"A store manager must never be able to see another store's data. This is a non-negotiable requirement."*

Currently, the `store_id` field exists on the `User` model but is **never read by any query**. When the dashboard is built, if a manager's `store_id` is not automatically applied as a filter to every data query, the isolation requirement will silently fail — and you will not notice until a manager accidentally sees another store's figures.

**The pattern to build:**

In `get_current_user`, return the `store_id` alongside the role. Any query made by a manager-role user must inject a `WHERE store_id = user.store_id` clause automatically — not rely on the frontend to request only the right store's data. The isolation must be enforced at the **database query level**, not the UI level.

---

## Section 7 — Testing

**There are no tests anywhere in this codebase.**

This is the most common omission in junior work, and it is the one that creates the most pain later. The PRD has 12 acceptance criteria that will be verified live in front of a client. Without automated tests, you cannot know if a change you made in Sprint 3 broke something you built in Sprint 1.

### What to build, in order of priority

**1. Backend: test the integrity check engine**

When built, this is the most business-critical logic in the system. A test that uploads a CSV with a negative price and asserts the correct exclusion count directly protects the client's data:

```python
def test_negative_price_is_excluded():
    csv_content = "product_id,quantity,unit_price\n1,2,-50.00\n2,1,100.00"
    response = client.post("/api/upload", files={"file": ("test.csv", csv_content)}, data={"store_id": 1})
    assert response.json()["total_excluded"] == 1
    assert response.json()["total_included"] == 1
```

**2. Backend: test data isolation**

Write a test that authenticates as a manager for Store A, makes a request for Store B's data, and asserts a `403` response. Run this in CI on every push:

```python
def test_manager_cannot_access_other_store():
    token = login_as("store_a_manager@retailpulse.com")
    response = client.get("/api/stores/2/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
```

**3. Frontend: test the login flow**

Use Vitest and React Testing Library:

```typescript
test('failed login shows error message', async () => {
  server.use(http.post('/login', () => HttpResponse.json({ detail: 'Invalid email or password.' }, { status: 401 })));
  render(<LoginPage />);
  await userEvent.type(screen.getByLabelText('Email address'), 'wrong@test.com');
  await userEvent.type(screen.getByLabelText('Password'), 'wrongpassword');
  await userEvent.click(screen.getByRole('button', { name: 'Sign In' }));
  expect(await screen.findByText('Invalid email or password.')).toBeInTheDocument();
});
```

---

## Summary Priority List

Fix these in order. The first three are blocking.

1. **The `/dashboard` route must exist** — the app is currently broken after login.
2. **The `localStorage` token storage must be replaced with `httpOnly` cookies** — this is a security vulnerability.
3. **The login error message must never expose `str(e)`** — this leaks internal details.
4. **The upload endpoint must stop returning fake success** — mark it `501 Not Implemented` until the engine is built.
5. **Environment variables must replace the hardcoded `localhost:8000` URL.**
6. **Route protection must be added before any dashboard page is built.**
7. **The data models must match the actual database schema.**
8. **The Alembic migration must not drop tables that contain data.**

---

## Closing Note

The overall trajectory here is correct. The authentication layer works, the RBAC pattern is right, the login design is clean, and the database schema (visible in the migration's `downgrade()`) is well thought out. The gaps are mostly about things that were started but not finished being treated as if they were complete.

In production, **"done" means it works correctly and safely end-to-end** — not that the function exists and returns a response.
