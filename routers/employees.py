"""Employee read endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from auth import require_api_key
from db import fetch_all_employees, fetch_employee

router = APIRouter()


@router.get("", tags=["employees"])
def list_employees(_: str = Depends(require_api_key)):
    return fetch_all_employees()


@router.get("/{employee_id}", tags=["employees"])
def get_employee(employee_id: str, _: str = Depends(require_api_key)):
    row = fetch_employee(employee_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )
    return row
