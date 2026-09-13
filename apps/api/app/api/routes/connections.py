import uuid
from datetime import datetime
from typing import Annotated

from cp_domain.connection import Connection, ConnectionPlatform, ConnectionStatus
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_membership
from app.core.celery_client import get_celery_client
from app.core.crypto import encrypt_credentials
from app.db.base import get_db
from app.db.models.membership import Membership

router = APIRouter(prefix="/connections", tags=["connections"])


class CreateConnectionRequest(BaseModel):
    platform: ConnectionPlatform
    name: str
    credentials: dict[str, str] = {}


class ConnectionOut(BaseModel):
    id: uuid.UUID
    platform: ConnectionPlatform
    name: str
    status: ConnectionStatus
    last_synced_at: datetime | None
    last_error: str | None

    model_config = {"from_attributes": True}


class SyncTriggeredResponse(BaseModel):
    task_id: str


@router.get("", response_model=list[ConnectionOut])
async def list_connections(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> list[Connection]:
    result = await db.scalars(
        select(Connection)
        .where(Connection.tenant_id == membership.tenant_id)
        .order_by(Connection.created_at.desc())
    )
    return list(result)


@router.post("", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: CreateConnectionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> Connection:
    connection = Connection(
        tenant_id=membership.tenant_id,
        platform=payload.platform,
        name=payload.name,
        status=ConnectionStatus.CONNECTED,
        encrypted_credentials=(
            encrypt_credentials(payload.credentials) if payload.credentials else None
        ),
    )
    db.add(connection)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A connection with this name already exists",
        ) from exc
    return connection


@router.post("/{connection_id}/sync", response_model=SyncTriggeredResponse)
async def trigger_sync(
    connection_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> SyncTriggeredResponse:
    connection = await db.scalar(
        select(Connection).where(
            Connection.id == connection_id, Connection.tenant_id == membership.tenant_id
        )
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    result = get_celery_client().send_task(
        "worker.sync_connection", args=[str(membership.tenant_id), str(connection.id)]
    )
    return SyncTriggeredResponse(task_id=result.id)
