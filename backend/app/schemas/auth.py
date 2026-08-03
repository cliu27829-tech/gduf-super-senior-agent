from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50, pattern=r"^[\w\-\u4e00-\u9fff]+$")
    nickname: str = Field(default="", max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    campus_id: str
    grade: str = Field(default="", max_length=32)
    major: str = Field(default="", max_length=100)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("密码至少包含一个字母和一个数字")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    username: str
    nickname: str
    role: str
    campus_id: str | None
    grade: str
    major: str
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserRead
    access_expires_at: datetime
    message: str = "登录成功"


class ProfileUpdate(BaseModel):
    nickname: str | None = Field(default=None, max_length=80)
    campus_id: str | None = None
    grade: str | None = Field(default=None, max_length=32)
    major: str | None = Field(default=None, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("新密码至少包含一个字母和一个数字")
        return value

