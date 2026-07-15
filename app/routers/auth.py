from fastapi import APIRouter, HTTPException, Depends, Request, Response
from pydantic import BaseModel, Field
from app.database import supabase, admin_supabase, get_db
from app.models import User, Store
from sqlalchemy.orm import Session
from typing import Optional
import logging
import os
from app.enums import UserRole

IS_PRODUCTION = os.getenv("ENVIRONMENT") == "production"


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

COOKIE_NAME = "access_token"


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    role: UserRole
    username: str
    store_id: Optional[int] = None
    confirm_replace: bool = False


# Pydantic schema for password changes
class UpdatePasswordRequest(BaseModel):
    new_password: str = Field(min_length=6)


def get_current_user(
        request: Request,
        db: Session = Depends(get_db)
):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user_response = supabase.auth.get_user(token)

        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        supabase_user = user_response.user

        profile = db.query(User).filter(
            User.auth_provider_id == supabase_user.id
        ).first()

        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        if not profile.is_active:
            raise HTTPException(status_code=403, detail="This account has been deactivated.")

        return {
            "id": str(supabase_user.id),
            "email": supabase_user.email,
            "role": UserRole(profile.role),
            "store_id": profile.store_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_current_user error: {e}")
        raise HTTPException(status_code=401, detail="Could not validate credentials")


def role_required(*roles: UserRole):
    def checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return Depends(checker)


@router.post("/login")
def login(credentials: LoginRequest, response: Response, db: Session = Depends(get_db)):
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })

        auth_id = str(auth_response.user.id)

        user_profile = db.query(User).filter(User.auth_provider_id == auth_id).first()

        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile not found in database")

        if not user_profile.is_active:
            raise HTTPException(status_code=403, detail="This account has been deactivated. Contact your administrator.")

        # Set httpOnly cookie
        response.set_cookie(
            key=COOKIE_NAME,
            value=auth_response.session.access_token,
            httponly=True,
            secure=True,  # Force True
            samesite="none",  # Force "none"
            max_age=3600,
        )

        return {"role": UserRole(user_profile.role)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error for {credentials.email}: {e}")
        raise HTTPException(status_code=401, detail="Invalid email or password.")


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=COOKIE_NAME,
        secure=True,
        samesite="none"
    )
    return {"message": "Logged out"}


@router.post("/admin/create-user")
def create_user(
        user_data: CreateUserRequest,
        db: Session = Depends(get_db),
        current_user=role_required(UserRole.OPS)
):
    try:
        if user_data.role == UserRole.OPS:
            existing_ops = db.query(User).filter(User.role == UserRole.OPS).count()
            if existing_ops >= 1:
                raise HTTPException(status_code=400, detail="An ops user already exists. Only one ops user is allowed.")

        existing_manager = None
        if user_data.role == UserRole.MANAGER:
            if not user_data.store_id:
                raise HTTPException(status_code=400, detail="A store must be assigned to a manager account.")
            store = db.query(Store).filter(Store.store_id == user_data.store_id).first()
            if not store:
                raise HTTPException(status_code=400, detail="Selected store does not exist.")

            existing_manager = db.query(User).filter(
                User.store_id == user_data.store_id,
                User.role == UserRole.MANAGER,
                User.is_active == True,
            ).first()

            if existing_manager and not user_data.confirm_replace:
                return {
                    "status": "manager_exists",
                    "message": (
                        f"{store.store_name} already has an active manager "
                        f"({existing_manager.username}). Replacing them will "
                        f"deactivate their account and they will no longer be "
                        f"able to log in."
                    ),
                    "existing_manager_username": existing_manager.username,
                    "store_name": store.store_name,
                }

        response = admin_supabase.auth.admin.create_user({
            "email": user_data.email,
            "password": user_data.password,
            "email_confirm": True
        })

        auth_id = str(response.user.id)


        if existing_manager and user_data.confirm_replace:
            existing_manager.is_active = False
            existing_manager.store_id = None
            db.flush()

        profile = db.query(User).filter(User.id == auth_id).first()

        if profile:
            profile.auth_provider_id = auth_id
            profile.username = user_data.username
            profile.role = user_data.role
            profile.store_id = user_data.store_id if user_data.role == UserRole.MANAGER else None
            profile.is_active = True
            db.commit()
            return {"status": "success", "message": "Existing profile updated", "user": response.user}

        new_profile = User(
            id=auth_id,
            username=user_data.username,
            role=user_data.role,
            auth_provider_id=auth_id,
            store_id=user_data.store_id if user_data.role == UserRole.MANAGER else None,
            is_active=True,
        )
        db.add(new_profile)
        db.commit()
        db.refresh(new_profile)

        return {"status": "success", "message": "User created successfully", "user": response.user}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"User creation error: {e}")
        raise HTTPException(status_code=400, detail="Failed to create user.")


# FIXED: Moved outside create_user to be its own independent endpoint
@router.post("/update-password")
def update_password(
        data: UpdatePasswordRequest,
        current_user=Depends(get_current_user)
):
    try:

        admin_supabase.auth.admin.update_user_by_id(
            current_user["id"],
            {"password": data.new_password}
        )
        return {"message": "Password updated successfully"}
    except Exception as e:
        logger.error(f"Password update error for user {current_user['email']}: {e}")
        raise HTTPException(status_code=400, detail="Failed to update password.")


@router.get("/admin/stores")
def list_stores(
        db: Session = Depends(get_db),
        current_user=role_required(UserRole.OPS)
):
    stores = db.query(Store).order_by(Store.store_name).all()
    return {
        "stores": [
            {
                "store_id": s.store_id,
                "store_name": s.store_name,
                "location": s.location,
            }
            for s in stores
        ]
    }


@router.get("/admin/users")
def list_users(
        db: Session = Depends(get_db),
        current_user=role_required(UserRole.OPS)
):
    rows = (
        db.query(User, Store.store_name, Store.location)
        .outerjoin(Store, Store.store_id == User.store_id)
        .filter(User.is_active == True)
        .order_by(User.role, User.username)
        .all()
    )
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "role": UserRole(u.role),
                "store_id": u.store_id,
                "store_name": store_name,
                "store_location": store_location,
            }
            for u, store_name, store_location in rows
        ]
    }