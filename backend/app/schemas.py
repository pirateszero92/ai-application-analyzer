from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

# --- Auth Schemas ---
class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserChangePassword(BaseModel):
    old_password: str
    new_password: str

class UserResponse(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True

# --- Settings Schemas ---
class SettingResponse(BaseModel):
    id: int
    loki_ip: str
    loki_projects: List[str]
    pmm_ip: str
    pmm_port: str
    pmm_user: str
    pmm_db_filters: List[str]
    ai_provider: str
    ai_host_url: str
    ai_model_name: str
    prometheus_ip: str
    prometheus_port: str
    discord_webhook_url: Optional[str]
    postgresql_conf: Optional[str]
    pgbouncer_ini: Optional[str]
    pg_hba_conf: Optional[str]
    lookback_minutes: int
    interval_minutes: int
    is_active: bool
    # Server hardware specs
    server_name: Optional[str] = None
    server_os: Optional[str] = None
    cpu_model: Optional[str] = None
    cpu_cores: Optional[int] = None
    ram_gb: Optional[int] = None
    storage_type: Optional[str] = None
    storage_size_gb: Optional[int] = None
    notes_for_ai: Optional[str] = None
    server_specs: Optional[List[dict]] = None  # multi-VM specs, parsed from server_specs_json
    db_connections: Optional[List[dict]] = None  # direct DB connections, parsed from db_connections_json
    # Proactive Monitoring
    proactive_enabled: bool = True
    proactive_interval_minutes: int = 2
    proactive_discord_enabled: bool = True

    class Config:
        from_attributes = True

class SettingUpdate(BaseModel):
    loki_ip: Optional[str] = None
    loki_projects: Optional[List[str]] = None
    pmm_ip: Optional[str] = None
    pmm_port: Optional[str] = None
    pmm_user: Optional[str] = None
    pmm_password: Optional[str] = None
    pmm_db_filters: Optional[List[str]] = None
    ai_provider: Optional[str] = None
    ai_host_url: Optional[str] = None
    ai_model_name: Optional[str] = None
    prometheus_ip: Optional[str] = None
    prometheus_port: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    postgresql_conf: Optional[str] = None
    pgbouncer_ini: Optional[str] = None
    pg_hba_conf: Optional[str] = None
    lookback_minutes: Optional[int] = None
    interval_minutes: Optional[int] = None
    is_active: Optional[bool] = None
    # Server hardware specs
    server_name: Optional[str] = None
    server_os: Optional[str] = None
    cpu_model: Optional[str] = None
    cpu_cores: Optional[int] = None
    ram_gb: Optional[int] = None
    storage_type: Optional[str] = None
    storage_size_gb: Optional[int] = None
    notes_for_ai: Optional[str] = None
    server_specs: Optional[List[dict]] = None  # multi-VM specs
    db_connections: Optional[List[dict]] = None  # direct DB connections
    # Proactive Monitoring
    proactive_enabled: Optional[bool] = None
    proactive_interval_minutes: Optional[int] = None
    proactive_discord_enabled: Optional[bool] = None


# --- Report Schemas ---
class ReportResponse(BaseModel):
    id: int
    timestamp: datetime
    status: str
    error_message: Optional[str] = None

    class Config:
        from_attributes = True

class ReportDetailResponse(BaseModel):
    id: int
    timestamp: datetime
    nginx_logs: Optional[str] = None
    slow_queries: Optional[str] = None
    prometheus_metrics: Optional[str] = None
    summary: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    minio_object_name: Optional[str] = None

    class Config:
        from_attributes = True

class DailySummaryResponse(BaseModel):
    id: int
    date: str
    summary: str
    total_runs: int
    success_runs: int
    failed_runs: int
    created_at: datetime

    class Config:
        from_attributes = True

class ChatMessageCreate(BaseModel):
    content: str

class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True


class HealthEventResponse(BaseModel):
    id: int
    timestamp: datetime
    health_score: int
    status: str
    alerts_json: Optional[str] = None
    metrics_json: Optional[str] = None
    ai_diagnosis: Optional[str] = None

    class Config:
        from_attributes = True
