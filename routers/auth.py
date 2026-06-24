from fastapi import APIRouter, HTTPException, Depends, Request, Response
from pydantic import BaseModel
from database import supabase, admin_supabase, get_db
from models import User
from sqlalchemy.orm import Session
from typing import Literal
import logging
import os
IS_PRODUCTION = os.getenv("ENVIRONMENT") == "production"


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

COOKIE_NAME = "access_token"


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: Literal["ops", "manager"]
    username: str


# Pydantic schema for password changes
class UpdatePasswordRequest(BaseModel):
    new_password: str


async def get_current_user(
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

        return {
            "id": str(supabase_user.id),
            "email": supabase_user.email,
            "role": profile.role,
            "store_id": profile.store_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_current_user error: {e}")
        raise HTTPException(status_code=401, detail="Could not validate credentials")


def role_required(*roles):
    async def checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return Depends(checker)


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return user


@router.post("/login")
async def login(credentials: LoginRequest, response: Response, db: Session = Depends(get_db)):
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })

        auth_id = str(auth_response.user.id)

        user_profile = db.query(User).filter(User.auth_provider_id == auth_id).first()

        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile not found in database")

        # Set httpOnly cookie
        response.set_cookie(
            key=COOKIE_NAME,
            value=auth_response.session.access_token,
            httponly=True,
            secure=True,  # Force True
            samesite="none",  # Force "none"
            max_age=3600,
        )

        return {"role": user_profile.role}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error for {credentials.email}: {e}")
        raise HTTPException(status_code=401, detail="Invalid email or password.")


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, samesite="lax")
    return {"message": "Logged out"}


@router.post("/admin/create-user")
async def create_user(
        user_data: CreateUserRequest,
        db: Session = Depends(get_db),
        current_user=role_required("ops")
):
    try:
        if user_data.role == "ops":
            existing_ops = db.query(User).filter(User.role == "ops").count()
            if existing_ops >= 1:
                raise HTTPException(status_code=400, detail="An ops user already exists. Only one ops user is allowed.")

        response = admin_supabase.auth.admin.create_user({
            "email": user_data.email,
            "password": user_data.password,
            "email_confirm": True
        })

        auth_id = str(response.user.id)

        profile = db.query(User).filter(User.id == auth_id).first()

        if profile:
            profile.auth_provider_id = auth_id
            profile.username = user_data.username
            profile.role = user_data.role
            db.commit()
            return {"message": "Existing profile updated", "user": response.user}

        new_profile = User(
            id=auth_id,
            username=user_data.username,
            role=user_data.role,
            auth_provider_id=auth_id
        )
        db.add(new_profile)
        db.commit()
        db.refresh(new_profile)

        return {"message": "User created successfully", "user": response.user}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"User creation error: {e}")
        raise HTTPException(status_code=400, detail="Failed to create user.")


# FIXED: Moved outside create_user to be its own independent endpoint
@router.post("/update-password")
async def update_password(
        data: UpdatePasswordRequest,
        current_user=Depends(get_current_user)
):
    try:
        # Use the admin client and target the user by id explicitly.
        # supabase.auth.update_user() relies on a session stored on the
        # client instance itself, but `supabase` is a single shared client
        # used by every request — it never has a per-user session set,
        # which is why this raised "Auth session missing!".
        admin_supabase.auth.admin.update_user_by_id(
            current_user["id"],
            {"password": data.new_password}
        )
        return {"message": "Password updated successfully"}
    except Exception as e:
        logger.error(f"Password update error for user {current_user['email']}: {e}")
        raise HTTPException(status_code=400, detail="Failed to update password.")