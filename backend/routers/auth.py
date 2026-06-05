from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from database import supabase, admin_supabase, get_db
from models import User
from sqlalchemy.orm import Session
from typing import Literal


router = APIRouter(tags=["Authentication"])
security = HTTPBearer()


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: Literal["ops", "manager"]
    username: str


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    token = credentials.credentials
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

        supabase_user.role = profile.role
        return supabase_user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


def role_required(*roles):
    async def checker(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return Depends(checker)


@router.post("/login")
async def login(credentials: LoginRequest):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        return {"access_token": response.session.access_token, "token_type": "bearer"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")


@router.post("/admin/create-user")
async def create_user(
    user_data: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user=role_required("ops")
):
    try:
        # prevent duplicate ops user
        if user_data.role == "ops":
            existing_ops = db.query(User).filter(User.role == "ops").count()
            if existing_ops >= 1:
                raise HTTPException(status_code=400, detail="An ops user already exists. Only one ops user is allowed.")

        # create in Supabase auth
        response = admin_supabase.auth.admin.create_user({
            "email": user_data.email,
            "password": user_data.password,
            "email_confirm": True
        })

        auth_id = str(response.user.id)

        # check if profile already exists
        profile = db.query(User).filter(User.id == auth_id).first()

        if profile:
            profile.auth_provider_id = auth_id
            profile.username = user_data.username
            profile.role = user_data.role
            db.commit()
            return {"message": "Existing profile updated", "user": response.user}

        # create new profile
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
        raise HTTPException(status_code=400, detail=str(e))