import os
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    loki_ip = Column(String, default="10.1.1.152")
    loki_projects = Column(String, default='["wms", "tms"]')  # JSON string
    
    pmm_ip = Column(String, default=os.getenv("PMM_DEFAULT_IP", "10.1.1.152"))
    pmm_port = Column(String, default=os.getenv("PMM_DEFAULT_PORT", "8443"))
    pmm_user = Column(String, default=os.getenv("PMM_DEFAULT_USER", "admin"))
    pmm_password = Column(String, default=os.getenv("PMM_DEFAULT_PASSWORD", ""))
    pmm_db_filters = Column(String, default='["wms", "tms"]')  # JSON string
    
    ai_provider = Column(String, default="lmstudio")  # lmstudio, ollama, custom_openai
    ai_host_url = Column(String, default="http://host.docker.internal:1234/v1")
    ai_model_name = Column(String, default="google/gemma-4-e4b")
    
    prometheus_ip = Column(String, default="10.1.1.152")
    prometheus_port = Column(String, default="9090")
    
    discord_webhook_url = Column(String, nullable=True)
    
    postgresql_conf = Column(Text, nullable=True)
    pgbouncer_ini = Column(Text, nullable=True)
    pg_hba_conf = Column(Text, nullable=True)
    
    lookback_minutes = Column(Integer, default=15)
    interval_minutes = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)

    # --- Server Hardware Specifications ---
    # These fields are injected into the AI system prompt to help the AI
    # give context-aware recommendations based on actual hardware capabilities.
    server_name = Column(String, nullable=True)         # e.g. "Production Server DC-01"
    server_os = Column(String, nullable=True)            # e.g. "Ubuntu 22.04 LTS"
    cpu_model = Column(String, nullable=True)            # e.g. "Intel Xeon E5-2690 v4"
    cpu_cores = Column(Integer, nullable=True)           # total logical cores
    ram_gb = Column(Integer, nullable=True)              # total RAM in GB
    storage_type = Column(String, nullable=True)         # HDD / SSD / NVMe
    storage_size_gb = Column(Integer, nullable=True)     # total storage in GB
    notes_for_ai = Column(Text, nullable=True)           # free-text context for AI
    server_specs_json = Column(Text, nullable=True)       # JSON array of multi-VM specs
    db_connections_json = Column(Text, nullable=True)     # JSON array of direct database connection settings

    # --- Proactive Monitoring Settings ---
    proactive_enabled = Column(Boolean, default=True)               # Toggle proactive monitoring on/off
    proactive_interval_minutes = Column(Integer, default=2)         # How often to run proactive check (minutes)
    proactive_discord_enabled = Column(Boolean, default=True)       # Send Discord alert on anomaly detected


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    nginx_logs = Column(Text, nullable=True)
    slow_queries = Column(Text, nullable=True)
    prometheus_metrics = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    status = Column(String, default="success")  # success, failed
    error_message = Column(Text, nullable=True)
    minio_object_name = Column(String, nullable=True)  # Path to raw archive in Minio

class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, unique=True, index=True, nullable=False)  # YYYY-MM-DD
    summary = Column(Text, nullable=False)
    total_runs = Column(Integer, default=0)
    success_runs = Column(Integer, default=0)
    failed_runs = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class HealthEvent(Base):
    """
    Stores results of proactive health checks.
    Created every time the proactive monitor runs and detects an anomaly,
    or periodically to record system health history.
    """
    __tablename__ = "health_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    health_score = Column(Integer, default=100)          # Overall health score 0-100
    status = Column(String, default="healthy")           # healthy / warning / critical
    alerts_json = Column(Text, nullable=True)            # JSON list of active alert messages
    metrics_json = Column(Text, nullable=True)           # JSON snapshot of raw metrics at time of check
    ai_diagnosis = Column(Text, nullable=True)           # Full AI root cause analysis (only when anomaly)


class BenchmarkReport(Base):
    """
    Stores historical performance benchmark run reports (HTTP & PostgreSQL).
    """
    __tablename__ = "benchmark_reports"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    name = Column(String, nullable=False)                    # Custom test name
    mode = Column(String, nullable=False)                    # 'http' or 'postgres'
    target_summary = Column(String, nullable=False)          # Target URL or DB Host/Query
    concurrent_users = Column(Integer, default=1)           # Number of simulated concurrent users
    duration_seconds = Column(Integer, default=10)           # Planned test duration
    total_operations = Column(Integer, default=0)           # Total HTTP requests or SQL queries
    success_operations = Column(Integer, default=0)         # Successful operations
    failed_operations = Column(Integer, default=0)          # Failed operations
    ops_per_sec = Column(Float, default=0.0)                 # RPS or QPS
    avg_latency_ms = Column(Float, default=0.0)              # Average latency in ms
    min_latency_ms = Column(Float, default=0.0)              # Min latency in ms
    max_latency_ms = Column(Float, default=0.0)              # Max latency in ms
    p50_ms = Column(Float, default=0.0)                      # p50 (Median) latency in ms
    p90_ms = Column(Float, default=0.0)                      # p90 percentile in ms
    p95_ms = Column(Float, default=0.0)                      # p95 percentile in ms
    p99_ms = Column(Float, default=0.0)                      # p99 percentile in ms
    status_breakdown_json = Column(Text, nullable=True)     # JSON breakdown of HTTP statuses or SQL errors
    metrics_timeline_json = Column(Text, nullable=True)     # JSON array of per-second timeline stats
    ai_recommendation = Column(Text, nullable=True)          # AI Performance Optimization analysis
    minio_object_name = Column(String, nullable=True)        # MinIO backup path
