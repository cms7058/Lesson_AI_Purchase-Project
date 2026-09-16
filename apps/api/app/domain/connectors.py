from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConnectorType(StrEnum):
    ERP = "erp"
    MES = "mes"
    SRM = "srm"
    QMS = "qms"
    WMS = "wms"
    AMOS = "amos"
    SAP = "sap"
    CONSIGNMENT = "consignment"
    VMI = "vmi"
    MINERU = "mineru"
    CUSTOM_API = "custom_api"


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    connector_type: ConnectorType
    base_url: str = Field(default="", max_length=500)
    sync_mode: str = Field(default="manual", pattern="^(manual|scheduled|webhook)$")


class ConnectorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    connector_type: ConnectorType | None = None
    base_url: str | None = Field(default=None, max_length=500)
    sync_mode: str | None = Field(default=None, pattern="^(manual|scheduled|webhook)$")
    status: str | None = Field(default=None, pattern="^(draft|active|disabled|error)$")


class DataConnector(ConnectorCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    created_by: str
    created_at: datetime
