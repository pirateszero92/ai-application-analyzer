import os
import threading
import json
import asyncio
from datetime import datetime
from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, Header, status, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import and_
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from .database import SessionLocal, engine, Base, get_db
from .models import User, Setting, Report, DailySummary, PeriodicSummary, ChatMessage, HealthEvent, BenchmarkReport
from .schemas import (
    UserLogin, Token, UserChangePassword, UserResponse,
    SettingResponse, SettingUpdate, ReportResponse, ReportDetailResponse,
    DailySummaryResponse, PeriodicSummaryResponse, ChatMessageCreate, ChatMessageResponse, HealthEventResponse
)
from .auth import (
    verify_password, get_password_hash, create_access_token, get_current_user
)
from .scheduler import start_scheduler, stop_scheduler, REDIS_URL
from .analyzer import run_analysis_job, generate_daily_ai_summary, generate_periodic_ai_summary, call_chat_ai
from .proactive_monitor import run_proactive_health_check

def safe_json_loads(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


# Webhook token for Prometheus Alertmanager authentication
ALERT_WEBHOOK_TOKEN = os.getenv("ALERT_WEBHOOK_TOKEN", "")

# Create Database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Log Analyzer API")

# Configure CORS
# In production, replace ["*"] with specific origin domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    # Initialize default admin user and default settings if they do not exist
    db = next(get_db())
    try:
        # 1. Default admin user (admin / admin)
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            hashed_pw = get_password_hash("admin")
            new_admin = User(username="admin", hashed_password=hashed_pw)
            db.add(new_admin)
            db.commit()
            print("[*] Created default admin user (admin/admin)")
            
        # 2. Default settings (ID=1)
        settings = db.query(Setting).filter(Setting.id == 1).first()
        if not settings:
            new_settings = Setting()
            db.add(new_settings)
            db.commit()
            print("[*] Created default application settings")
    except Exception as e:
        print(f"[!] Startup database initialization failed: {str(e)}")
    finally:
        db.close()
        
    # Start the periodic background scheduler
    start_scheduler()

@app.on_event("shutdown")
def shutdown_event():
    stop_scheduler()

# --- Auth Routes ---

@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.post("/api/auth/change-password")
def change_password(data: UserChangePassword, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )
    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Password changed successfully"}

# --- Settings Routes ---

@app.get("/api/settings", response_model=SettingResponse)
def get_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Settings not found")
    
    # Parse JSON strings to lists safely
    return SettingResponse(
        id=setting.id,
        loki_ip=setting.loki_ip,
        loki_projects=safe_json_loads(setting.loki_projects, []),
        pmm_ip=setting.pmm_ip,
        pmm_port=setting.pmm_port,
        pmm_user=setting.pmm_user,
        pmm_db_filters=safe_json_loads(setting.pmm_db_filters, []),
        ai_provider=setting.ai_provider,
        ai_host_url=setting.ai_host_url,
        ai_model_name=setting.ai_model_name,
        prometheus_ip=setting.prometheus_ip,
        prometheus_port=setting.prometheus_port,
        discord_webhook_url=setting.discord_webhook_url,
        postgresql_conf=setting.postgresql_conf,
        pgbouncer_ini=setting.pgbouncer_ini,
        pg_hba_conf=setting.pg_hba_conf,
        lookback_minutes=setting.lookback_minutes,
        interval_minutes=setting.interval_minutes,
        is_active=setting.is_active,
        server_name=setting.server_name,
        server_os=setting.server_os,
        cpu_model=setting.cpu_model,
        cpu_cores=setting.cpu_cores,
        ram_gb=setting.ram_gb,
        storage_type=setting.storage_type,
        storage_size_gb=setting.storage_size_gb,
        notes_for_ai=setting.notes_for_ai,
        server_specs=safe_json_loads(setting.server_specs_json, []),
        db_connections=safe_json_loads(setting.db_connections_json, []),
        proactive_enabled=getattr(setting, "proactive_enabled", True) if getattr(setting, "proactive_enabled", True) is not None else True,
        proactive_interval_minutes=getattr(setting, "proactive_interval_minutes", 2) or 2,
        proactive_discord_enabled=getattr(setting, "proactive_discord_enabled", True) if getattr(setting, "proactive_discord_enabled", True) is not None else True
    )

@app.put("/api/settings", response_model=SettingResponse)
def update_settings(data: SettingUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Settings not found")
        
    # Apply updates
    if data.loki_ip is not None:
        setting.loki_ip = data.loki_ip
    if data.loki_projects is not None:
        setting.loki_projects = json.dumps(data.loki_projects)
    if data.pmm_ip is not None:
        setting.pmm_ip = data.pmm_ip
    if data.pmm_port is not None:
        setting.pmm_port = data.pmm_port
    if data.pmm_user is not None:
        setting.pmm_user = data.pmm_user
    if data.pmm_password is not None:
        setting.pmm_password = data.pmm_password
    if data.pmm_db_filters is not None:
        setting.pmm_db_filters = json.dumps(data.pmm_db_filters)
    if data.ai_provider is not None:
        setting.ai_provider = data.ai_provider
    if data.ai_host_url is not None:
        setting.ai_host_url = data.ai_host_url
    if data.ai_model_name is not None:
        setting.ai_model_name = data.ai_model_name
    if data.prometheus_ip is not None:
        setting.prometheus_ip = data.prometheus_ip
    if data.prometheus_port is not None:
        setting.prometheus_port = data.prometheus_port
    if data.discord_webhook_url is not None:
        setting.discord_webhook_url = data.discord_webhook_url
    if data.postgresql_conf is not None:
        setting.postgresql_conf = data.postgresql_conf
    if data.pgbouncer_ini is not None:
        setting.pgbouncer_ini = data.pgbouncer_ini
    if data.pg_hba_conf is not None:
        setting.pg_hba_conf = data.pg_hba_conf
    if data.lookback_minutes is not None:
        setting.lookback_minutes = data.lookback_minutes
    if data.interval_minutes is not None:
        setting.interval_minutes = data.interval_minutes
    if data.is_active is not None:
        setting.is_active = data.is_active
    # Server hardware specs
    if data.server_name is not None:
        setting.server_name = data.server_name
    if data.server_os is not None:
        setting.server_os = data.server_os
    if data.cpu_model is not None:
        setting.cpu_model = data.cpu_model
    if data.cpu_cores is not None:
        setting.cpu_cores = data.cpu_cores
    if data.ram_gb is not None:
        setting.ram_gb = data.ram_gb
    if data.storage_type is not None:
        setting.storage_type = data.storage_type
    if data.storage_size_gb is not None:
        setting.storage_size_gb = data.storage_size_gb
    if data.notes_for_ai is not None:
        setting.notes_for_ai = data.notes_for_ai
    if data.server_specs is not None:
        setting.server_specs_json = json.dumps(data.server_specs, ensure_ascii=False)
    if data.db_connections is not None:
        setting.db_connections_json = json.dumps(data.db_connections, ensure_ascii=False)
    # Proactive Monitoring
    if data.proactive_enabled is not None:
        setting.proactive_enabled = data.proactive_enabled
    if data.proactive_interval_minutes is not None:
        setting.proactive_interval_minutes = data.proactive_interval_minutes
    if data.proactive_discord_enabled is not None:
        setting.proactive_discord_enabled = data.proactive_discord_enabled
        
    db.commit()
    
    # Return formatted response safely
    return SettingResponse(
        id=setting.id,
        loki_ip=setting.loki_ip,
        loki_projects=safe_json_loads(setting.loki_projects, []),
        pmm_ip=setting.pmm_ip,
        pmm_port=setting.pmm_port,
        pmm_user=setting.pmm_user,
        pmm_db_filters=safe_json_loads(setting.pmm_db_filters, []),
        ai_provider=setting.ai_provider,
        ai_host_url=setting.ai_host_url,
        ai_model_name=setting.ai_model_name,
        prometheus_ip=setting.prometheus_ip,
        prometheus_port=setting.prometheus_port,
        discord_webhook_url=setting.discord_webhook_url,
        postgresql_conf=setting.postgresql_conf,
        pgbouncer_ini=setting.pgbouncer_ini,
        pg_hba_conf=setting.pg_hba_conf,
        lookback_minutes=setting.lookback_minutes,
        interval_minutes=setting.interval_minutes,
        is_active=setting.is_active,
        server_name=setting.server_name,
        server_os=setting.server_os,
        cpu_model=setting.cpu_model,
        cpu_cores=setting.cpu_cores,
        ram_gb=setting.ram_gb,
        storage_type=setting.storage_type,
        storage_size_gb=setting.storage_size_gb,
        notes_for_ai=setting.notes_for_ai,
        server_specs=safe_json_loads(setting.server_specs_json, []),
        db_connections=safe_json_loads(setting.db_connections_json, []),
        proactive_enabled=getattr(setting, "proactive_enabled", True) if getattr(setting, "proactive_enabled", True) is not None else True,
        proactive_interval_minutes=getattr(setting, "proactive_interval_minutes", 2) or 2,
        proactive_discord_enabled=getattr(setting, "proactive_discord_enabled", True) if getattr(setting, "proactive_discord_enabled", True) is not None else True
    )


# --- Reports Routes ---

@app.get("/api/reports", response_model=List[ReportResponse])
def list_reports(limit: int = 50, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reports = db.query(Report).order_by(Report.timestamp.desc()).limit(limit).all()
    return reports

@app.get("/api/reports/daily-summary", response_model=DailySummaryResponse)
def get_daily_summary(
    date: str,
    force: bool = False,
    generate: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Validate date format
    try:
        query_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="รูปแบบวันที่ไม่ถูกต้อง กรุณาใช้ YYYY-MM-DD")

    # 2. Fetch all reports on that calendar date
    start_dt = datetime.combine(query_date, datetime.min.time())
    end_dt = datetime.combine(query_date, datetime.max.time())

    reports = db.query(Report).filter(
        and_(
            Report.timestamp >= start_dt,
            Report.timestamp <= end_dt
        )
    ).order_by(Report.timestamp.asc()).all()

    if not reports:
        raise HTTPException(status_code=404, detail="ไม่พบประวัติงานรันวิเคราะห์ในวันที่ระบุ")

    # Calculate stats
    total_runs = len(reports)
    success_runs = sum(1 for r in reports if r.status == "success")
    failed_runs = sum(1 for r in reports if r.status == "failed")

    # 3. Check for cached summary
    cached = db.query(DailySummary).filter(DailySummary.date == date).first()
    is_today = query_date == datetime.now().date()

    # If cache exists, and we are not forcing a refresh, AND:
    # - either it's NOT today
    # - OR it is today but the client is not requesting to (re)generate a fresh AI summary
    if cached and not force and (not is_today or not generate):
        return cached

    # If no cache exists, and the user did NOT request to generate one:
    if not generate:
        raise HTTPException(
            status_code=404, 
            detail="ยังไม่ได้สรุปวิเคราะห์ภาพรวมประจำวันนี้ กดปุ่มด้านบนเพื่อสั่งรันวิเคราะห์ระบบรายวันได้ทันที"
        )

    # 4. Generate AI summary
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        raise HTTPException(status_code=500, detail="ไม่พบการตั้งค่าในระบบ")

    summary_text = generate_daily_ai_summary(
        setting.ai_provider,
        setting.ai_host_url,
        setting.ai_model_name,
        date,
        reports
    )

    # 5. Save to cache
    if cached:
        cached.summary = summary_text
        cached.total_runs = total_runs
        cached.success_runs = success_runs
        cached.failed_runs = failed_runs
        db.commit()
        db.refresh(cached)
        return cached
    else:
        new_summary = DailySummary(
            date=date,
            summary=summary_text,
            total_runs=total_runs,
            success_runs=success_runs,
            failed_runs=failed_runs
        )
        db.add(new_summary)
        db.commit()
        db.refresh(new_summary)
        return new_summary



@app.get("/api/reports/daily-summaries", response_model=List[DailySummaryResponse])
def list_daily_summaries(
    limit: int = 60,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns a list of all available daily summary records, ordered by date descending.
    Used to populate the date navigation panel in the Daily Summary page.
    """
    summaries = db.query(DailySummary).order_by(DailySummary.date.desc()).limit(limit).all()
    return summaries


@app.get("/api/reports/periodic-summary", response_model=PeriodicSummaryResponse)
def get_periodic_summary(
    period_type: str,     # 'weekly' or 'monthly'
    period_key: str,      # '2026-W35' (weekly) or '2026-08' (monthly)
    force: bool = False,
    generate: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fetches or generates a 7-day Weekly or 30-day Monthly Executive Summary with AI.
    Analyzes historical trends, chronic slow queries, and infrastructure capacity growth.
    """
    import calendar
    from datetime import date as dt_date

    # 1. Validate and calculate date range
    if period_type == "weekly":
        try:
            parts = period_key.split("-W")
            year, week = int(parts[0]), int(parts[1])
            first_day = dt_date.fromisocalendar(year, week, 1)
            last_day = dt_date.fromisocalendar(year, week, 7)
            start_date_str = first_day.strftime("%Y-%m-%d")
            end_date_str = last_day.strftime("%Y-%m-%d")
            period_label = f"สัปดาห์ที่ {week} ({first_day.strftime('%d/%m')} - {last_day.strftime('%d/%m/%Y')})"
        except Exception:
            raise HTTPException(status_code=400, detail="รูปแบบรหัสสัปดาห์ไม่ถูกต้อง กรุณาใช้ YYYY-Www (เช่น 2026-W35)")
    elif period_type == "monthly":
        try:
            parts = period_key.split("-")
            year, month = int(parts[0]), int(parts[1])
            first_day = dt_date(year, month, 1)
            last_day_num = calendar.monthrange(year, month)[1]
            last_day = dt_date(year, month, last_day_num)
            start_date_str = first_day.strftime("%Y-%m-%d")
            end_date_str = last_day.strftime("%Y-%m-%d")
            month_names_th = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
            month_name = month_names_th[month] if month <= 12 else str(month)
            period_label = f"เดือน {month_name} {year}"
        except Exception:
            raise HTTPException(status_code=400, detail="รูปแบบรหัสเดือนไม่ถูกต้อง กรุณาใช้ YYYY-MM (เช่น 2026-08)")
    else:
        raise HTTPException(status_code=400, detail="period_type ต้องเป็น 'weekly' หรือ 'monthly'")

    # 2. Check cached summary
    cached = db.query(PeriodicSummary).filter(
        PeriodicSummary.period_type == period_type,
        PeriodicSummary.period_key == period_key
    ).first()

    # If cached exists and not forcing refresh, return it
    if cached and not force and not generate:
        return cached

    # 3. Query all reports in date range (30-day live log window)
    start_dt = datetime.combine(first_day, datetime.min.time())
    end_dt = datetime.combine(last_day, datetime.max.time())

    reports = db.query(Report).filter(
        and_(Report.timestamp >= start_dt, Report.timestamp <= end_dt)
    ).order_by(Report.timestamp.asc()).all()

    # Query health events and daily summaries in range
    health_events = db.query(HealthEvent).filter(
        and_(HealthEvent.timestamp >= start_dt, HealthEvent.timestamp <= end_dt)
    ).order_by(HealthEvent.timestamp.asc()).all()

    daily_summaries = db.query(DailySummary).filter(
        and_(DailySummary.date >= start_date_str, DailySummary.date <= end_date_str)
    ).order_by(DailySummary.date.asc()).all()

    if not reports and not health_events:
        raise HTTPException(status_code=404, detail=f"ไม่พบประวัติงานรันวิเคราะห์ในช่วง {period_label}")

    total_runs = len(reports)
    success_runs = sum(1 for r in reports if r.status == "success")
    failed_runs = sum(1 for r in reports if r.status == "failed")
    avg_score = 100.0
    if health_events:
        avg_score = sum(h.health_score for h in health_events) / len(health_events)

    if not generate and not cached:
        raise HTTPException(
            status_code=404,
            detail=f"ยังไม่ได้สร้างรายงานสรุป {period_label} กดปุ่ม 'สั่ง AI สรุปรายงาน' เพื่อสร้างได้ทันที"
        )

    # 4. Generate AI summary
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        raise HTTPException(status_code=500, detail="ไม่พบการตั้งค่าในระบบ")

    summary_text = generate_periodic_ai_summary(
        provider=setting.ai_provider,
        host_url=setting.ai_host_url,
        model_name=setting.ai_model_name,
        period_type=period_type,
        period_label=period_label,
        start_date=start_date_str,
        end_date=end_date_str,
        reports=reports,
        health_events=health_events,
        daily_summaries=daily_summaries
    )

    # 5. Save to database
    if cached:
        cached.title = period_label
        cached.summary = summary_text
        cached.total_runs = total_runs
        cached.success_runs = success_runs
        cached.failed_runs = failed_runs
        cached.avg_health_score = round(avg_score, 1)
        cached.incident_count = len(health_events)
        db.commit()
        db.refresh(cached)
        return cached
    else:
        new_summary = PeriodicSummary(
            period_type=period_type,
            period_key=period_key,
            title=period_label,
            start_date=start_date_str,
            end_date=end_date_str,
            summary=summary_text,
            total_runs=total_runs,
            success_runs=success_runs,
            failed_runs=failed_runs,
            avg_health_score=round(avg_score, 1),
            incident_count=len(health_events)
        )
        db.add(new_summary)
        db.commit()
        db.refresh(new_summary)
        return new_summary


@app.get("/api/reports/periodic-summaries", response_model=List[PeriodicSummaryResponse])
def list_periodic_summaries(
    period_type: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns historical weekly or monthly executive summaries.
    """
    q = db.query(PeriodicSummary)
    if period_type:
        q = q.filter(PeriodicSummary.period_type == period_type)
    return q.order_by(PeriodicSummary.id.desc()).limit(limit).all()


@app.get("/api/reports/retention-status")
def get_log_retention_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the log retention policy status (30-day live logs & archives in MinIO).
    """
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    total_reports = db.query(Report).count()
    reports_in_30d = db.query(Report).filter(Report.timestamp >= thirty_days_ago).count()
    oldest_report = db.query(Report).order_by(Report.timestamp.asc()).first()
    total_health_events = db.query(HealthEvent).count()
    daily_summaries_count = db.query(DailySummary).count()
    periodic_summaries_count = db.query(PeriodicSummary).count()

    return {
        "retention_policy_days": 30,
        "total_historical_reports": total_reports,
        "reports_within_30_days": reports_in_30d,
        "total_proactive_health_events": total_health_events,
        "total_daily_summaries": daily_summaries_count,
        "total_periodic_summaries": periodic_summaries_count,
        "oldest_log_timestamp": oldest_report.timestamp.isoformat() if oldest_report and oldest_report.timestamp else None,
        "storage_mode": "PostgreSQL Metadata + MinIO Object Storage 30-day Archive"
    }


@app.get("/api/reports/{report_id}", response_model=ReportDetailResponse)
def get_report(report_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report

def _run_analysis_in_new_session(report_id: int):
    """
    Background wrapper that creates its own DB session to avoid use-after-close race condition.
    FastAPI closes the request's DB session after the response is returned, so background
    tasks must not share the request's session object.
    """
    db = SessionLocal()
    try:
        run_analysis_job(db, report_id)
    finally:
        db.close()

@app.post("/api/reports/trigger", response_model=ReportResponse)
def trigger_analysis(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Create report running placeholder
    report = Report(status="running")
    db.add(report)
    db.commit()
    db.refresh(report)
    report_id = report.id  # Extract ID before session closes
    
    # Pass only report_id (not the session object) to background task
    background_tasks.add_task(_run_analysis_in_new_session, report_id)
    
    return report

@app.delete("/api/reports/{report_id}")
def delete_report(report_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
        
    # 1. Delete from MinIO if it exists
    if report.minio_object_name:
        try:
            from .storage import get_minio_client
            client = get_minio_client()
            if client:
                client.remove_object("reports", report.minio_object_name)
                print(f"[*] Deleted MinIO object: {report.minio_object_name}")
        except Exception as e:
            print(f"[!] Failed to delete MinIO object: {str(e)}")
            
    # 2. Delete from database
    db.delete(report)
    db.commit()
    return {"message": "Report deleted successfully"}

def run_proactive_analysis(alert_details: dict, setting_id: int):
    """
    Background worker that runs DevOps AI analysis triggered by a real-time Prometheus alert.
    Sends progress and diagnosis directly to Discord.
    """
    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.id == setting_id).first()
        if not setting or not setting.discord_webhook_url:
            print("[!] Discord Webhook URL is not configured. Skipping proactive analysis.")
            return

        from .notifier import send_discord_alert
        
        alertname = alert_details.get("alertname", "Unknown Alert")
        container = alert_details.get("container", "Unknown")
        description = alert_details.get("description", "No description provided")
        project = alert_details.get("project", "wms")

        # 1. Notify Discord: Analysis Started
        title = f"🚨 Alert Triggered: {alertname} ({project.upper()})"
        desc = (
            f"**Status**: `firing`\n"
            f"**Target Container/Host**: `{container}`\n"
            f"**Details**: {description}\n\n"
            f"🤖 *DevOps AI Agent is pulling Loki logs, PMM queries, and Prometheus metrics for analysis...*"
        )
        send_discord_alert(setting.discord_webhook_url, title, desc, color=15548997)

        # 2. Run analysis
        report = Report(status="running")
        db.add(report)
        db.commit()
        db.refresh(report)

        run_analysis_job(db, report.id)

        # Fetch report again to send follow-up
        db.refresh(report)
        if report.status == "success":
            follow_up_title = f"✅ DevOps AI Diagnostic Report: Run #{report.id}"
            ai_summary = report.summary or "วิเคราะห์สำเร็จ แต่ไม่มีผลสรุปจาก AI"
            send_discord_alert(setting.discord_webhook_url, follow_up_title, ai_summary, color=5763719)
        else:
            error_title = f"❌ DevOps AI Analysis Failed: Run #{report.id}"
            send_discord_alert(setting.discord_webhook_url, error_title, report.error_message or "Unknown Error", color=15548997)

    except Exception as e:
        print(f"[!] Proactive analysis failed: {str(e)}")
    finally:
        db.close()

@app.post("/api/alerts/webhook")
def receive_prometheus_alert(
    payload: dict,
    background_tasks: BackgroundTasks,
    x_webhook_token: Optional[str] = Header(None)
):
    """
    Receives Prometheus Alertmanager or Grafana Alert webhook payloads,
    and runs a targeted DevOps AI analysis in the background.
    Secured with a shared token via X-Webhook-Token header.
    """
    # Validate webhook token
    if not ALERT_WEBHOOK_TOKEN:
        raise HTTPException(status_code=503, detail="Webhook endpoint is not configured (ALERT_WEBHOOK_TOKEN environment variable not set)")
    if x_webhook_token != ALERT_WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing webhook token")

    print(f"[*] Received Alert Webhook payload: {payload}")
    
    alerts = payload.get("alerts", [])
    if not alerts:
        # Check if Grafana Alert payload format
        if "title" in payload and "message" in payload:
            alert_details = {
                "alertname": payload.get("title", "Grafana Alert"),
                "container": "Grafana Target",
                "description": payload.get("message", "Alert details"),
                "project": "wms"
            }
            background_tasks.add_task(run_proactive_analysis, alert_details, 1)
            return {"status": "Grafana alert scheduled"}
        return {"status": "No alerts found in payload"}

    for alert in alerts:
        if alert.get("status") == "firing":
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            
            container = labels.get("container", labels.get("instance", "unknown"))
            job = labels.get("job", "")
            project = "wms" if "wms" in (container + job).lower() else "tms" if "tms" in (container + job).lower() else "wms"
            
            alert_details = {
                "alertname": labels.get("alertname", "Unknown Alert"),
                "container": container,
                "description": annotations.get("description", annotations.get("summary", "No details")),
                "project": project
            }
            
            background_tasks.add_task(run_proactive_analysis, alert_details, 1)
            print(f"[*] Scheduled proactive analysis for alert: {alert_details['alertname']}")
            if len(alerts) > 1:
                print(f"[!] Warning: {len(alerts) - 1} additional alert(s) in batch were not processed (only first firing alert handled)")
            break
            
    return {"status": "Alert processed"}

# --- Chat Assistant Endpoints ---

@app.get("/api/chat/messages", response_model=List[ChatMessageResponse])
def get_chat_messages(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ดึงรายการข้อความสนทนาทั้งหมด เรียงจากเก่าไปใหม่ เพื่อนำไปแสดงผลบนหน้าต่างแชท
    """
    messages = db.query(ChatMessage).order_by(ChatMessage.timestamp.asc()).all()
    return messages

def fetch_live_system_telemetry(db: Session = None) -> str:
    """
    Fetches real-time live infrastructure telemetry from Prometheus (10.1.1.152:9090)
    and probes live database connections configured in Settings.
    """
    import urllib.request
    import json
    import psycopg2
    
    telemetry = []
    base_url = "http://10.1.1.152:9090/api/v1/query?query="
    
    # 1. Check Container Down status
    try:
        url = base_url + "time()-container_last_seen{name!=%22%22}>30"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            down_containers = [i['metric'].get('name') for i in data.get('data', {}).get('result', []) if i['metric'].get('name')]
            if down_containers:
                telemetry.append(f"⚠️ พบ Container ที่ DOWN/Crashed ขณะนี้: {', '.join(down_containers[:5])}")
            else:
                telemetry.append("✅ สถานะ Containers ทั้งหมด: ปกติ (ไม่มี Container Down/Stale ในระบบ)")
    except Exception:
        pass

    # 2. Check Node CPU Load
    try:
        url = base_url + "100-(avg(rate(node_cpu_seconds_total{mode=%22idle%22}[1m]))*100)"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            res = data.get('data', {}).get('result', [])
            if res:
                cpu_val = float(res[0]['value'][1])
                telemetry.append(f"📊 Node CPU Usage สดขณะนี้: {cpu_val:.1f}%")
    except Exception:
        pass

    # 3. Live probe configured Database Connections
    if db:
        try:
            setting = db.query(Setting).filter(Setting.id == 1).first()
            if setting and setting.db_connections_json:
                db_conns = json.loads(setting.db_connections_json)
                for conn_info in db_conns:
                    label = conn_info.get("label", conn_info.get("host"))
                    host = conn_info.get("host")
                    port = int(conn_info.get("port", 5432))
                    dbname = conn_info.get("dbname")
                    user = conn_info.get("user")
                    password = conn_info.get("password")
                    try:
                        c = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=3)
                        cur = c.cursor()
                        # Query active connections count vs max
                        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE state != 'idle' AND pid != pg_backend_pid()")
                        active_cnt = cur.fetchone()[0] or 0
                        cur.execute("SHOW max_connections")
                        max_cnt = int(cur.fetchone()[0] or 100)
                        conn_pct = (active_cnt / max_cnt * 100) if max_cnt > 0 else 0

                        # Probe real-time long queries (>5s) or lock contention
                        cur.execute("""
                            SELECT pid, state, wait_event_type, wait_event, pg_blocking_pids(pid) AS blocking,
                                   ROUND(EXTRACT(epoch FROM (now() - query_start))) AS dur,
                                   SUBSTRING(query FROM 1 FOR 100) AS q
                            FROM pg_stat_activity
                            WHERE state != 'idle' AND pid != pg_backend_pid()
                              AND backend_type != 'walsender'
                              AND query NOT ILIKE 'START_REPLICATION%'
                              AND query NOT ILIKE 'autovacuum:%'
                              AND query_start IS NOT NULL
                              AND EXTRACT(epoch FROM (now() - query_start)) > 5
                            ORDER BY dur DESC LIMIT 3
                        """)
                        slow_rows = cur.fetchall()
                        cur.close()
                        c.close()

                        db_line = f"🐘 [SUCCESS] ฐานข้อมูล {label} ({host}:{port}/{dbname}): เชื่อมต่อได้ปกติ 100% (Active Connections: {active_cnt}/{max_cnt} - {conn_pct:.0f}%)"
                        if slow_rows:
                            db_line += f"\n   ⚠️ ตรวจพบคิวรีรันนาน >5s หรือติด Lock ขณะนี้ {len(slow_rows)} รายการ:"
                            for r in slow_rows:
                                pid, state, wait_type, wait_ev, blocking, dur, q_text = r
                                block_str = f" [⛔ ติด Lock โดย PID {blocking}]" if blocking else ""
                                wait_str = f" (รอ {wait_type}/{wait_ev})" if wait_type else ""
                                db_line += f"\n   - PID {pid} รัน {dur}s{block_str}{wait_str}: {q_text}"
                        telemetry.append(db_line)
                    except Exception as e:
                        err_msg = str(e).strip().replace('\n', ' ')
                        telemetry.append(f"🐘 [FAILED] ฐานข้อมูล {label} ({host}:{port}/{dbname}): ❌ เชื่อมต่อไม่ได้! สาเหตุ: {err_msg}")
        except Exception as ex:
            print(f"[!] Error probing DB connections in telemetry: {ex}")

    if telemetry:
        return "\n\n[ข้อมูลสถานะ Real-time สดจากระบบ ณ วินาทีนี้ที่ AI ตรวจสอบจริงล่วงหน้าก่อนให้คำแนะนำ]:\n" + "\n".join(telemetry)
    return ""


@app.post("/api/chat/messages", response_model=ChatMessageResponse)
def send_chat_message(
    chat_msg: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ส่งคำถามหา AI บันทึกข้อความและคำตอบลงในหน่วยความจำฐานข้อมูล
    """
    # 1. Fetch history BEFORE inserting user message to avoid duplication in AI payload
    # (Limit 19 to leave room for the new user message = 20 total context messages)
    history_records = db.query(ChatMessage).order_by(ChatMessage.timestamp.desc()).limit(19).all()
    history_records.reverse()  # Sort chronologically

    # 2. Save user message to database
    user_message = ChatMessage(role="user", content=chat_msg.content)
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # 3. Get active setting (for AI provider configs)
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        ai_reply = "ไม่พบการตั้งค่าในระบบ กรุณาตั้งค่า AI Provider ที่หน้า Settings ก่อนเริ่มใช้งาน"
    else:
        # 5.2 Fetch live telemetry metrics & live DB connection probes
        live_telemetry_context = fetch_live_system_telemetry(db=db)

        # 4. Build context messages (history + new user message)
        messages_history = []
        for r in history_records:
            content = r.content
            # Sanitize past refusal hallucination messages from context
            if r.role == "assistant" and ("ไม่สามารถเชื่อมต่อ" in content or "ไม่มีความสามารถในการเชื่อมต่อ" in content or "ข้อจำกัดทางเทคนิค" in content or "ไม่มีเครื่องมือในการเชื่อมต่อ" in content):
                content = "[หมายเหตุ: ระบบเอนจินหลังบ้านได้ทำการทดสอบเชื่อมต่อจริงเรียบร้อยแล้ว]"
            messages_history.append({"role": r.role, "content": content})

        user_prompt_content = chat_msg.content
        if any(w in user_prompt_content.lower() for w in ["เชื่อมต่อ", "connect", "tms", "wms", "db"]):
            user_prompt_content += f"\n\n{live_telemetry_context}"

        messages_history.append({"role": "user", "content": user_prompt_content})
        latest_report = db.query(Report).filter(Report.status == "success").order_by(Report.timestamp.desc()).first()
        report_context = ""
        if latest_report and latest_report.summary and latest_report.timestamp:
            try:
                # Calculate daily index of this report (count reports on the same day up to this timestamp)
                report_date = latest_report.timestamp.date()
                start_of_day = datetime.combine(report_date, datetime.min.time())
                
                daily_index = db.query(Report).filter(
                    and_(
                        Report.timestamp >= start_of_day,
                        Report.timestamp <= latest_report.timestamp
                    )
                ).count()
                
                report_date_str = report_date.strftime("%d/%m/%Y")
                
                report_context = (
                    f"\n\n[ข้อมูลสถานะและคอขวดปัจจุบันของระบบจริงจากรอบรันวิเคราะห์ล่าสุดของวันนี้: Run #{daily_index} ({report_date_str})]:\n"
                    f"{latest_report.summary}\n\n"
                    f"คำแนะนำสำคัญ: เมื่อคุณอ้างอิงถึงรอบวิเคราะห์ล่าสุดนี้ "
                    f"จงเรียกชื่อรอบวิเคราะห์นี้ว่า 'Run #{daily_index}' หรือ 'รอบวิเคราะห์ที่ {daily_index} ของวันนี้ ({report_date_str})' เสมอ "
                    f"เพื่อให้สอดคล้องกับเลขลำดับที่ผู้ใช้เห็นบนหน้าจอด้านซ้าย (ห้ามเรียกด้วยเลข ID #{latest_report.id} จากฝั่งฐานข้อมูลเด็ดขาด)"
                )
            except Exception as ex:
                print(f"[!] Error building report_context for chat: {ex}")
                report_context = f"\n\n[ข้อมูลสถานะล่าสุด]:\n{latest_report.summary}"

        # 5.1 Fetch the latest Benchmark Report (Benchmark Test Suite)
        latest_benchmark = db.query(BenchmarkReport).order_by(BenchmarkReport.timestamp.desc()).first()
        benchmark_context = ""
        if latest_benchmark:
            try:
                benchmark_date_str = latest_benchmark.timestamp.strftime("%d/%m/%Y %H:%M:%S") if latest_benchmark.timestamp else ""
                benchmark_context = (
                    f"\n\n[ข้อมูลการทดสอบประสิทธิภาพล่าสุดจากโมดูล Benchmark Test Suite (Benchmark Report #{latest_benchmark.id}) - {benchmark_date_str}]:\n"
                    f"- ชื่อการทดสอบ: {latest_benchmark.name}\n"
                    f"- โหมด: {latest_benchmark.mode.upper()} ({latest_benchmark.target_summary})\n"
                    f"- Concurrent Users: {latest_benchmark.concurrent_users} users (ระยะเวลา {latest_benchmark.duration_seconds}s)\n"
                    f"- Total Operations: {latest_benchmark.total_operations} (สำเร็จ: {latest_benchmark.success_operations}, ล้มเหลว: {latest_benchmark.failed_operations})\n"
                    f"- Throughput: {latest_benchmark.ops_per_sec:.1f} ops/s\n"
                    f"- Latency: Avg {latest_benchmark.avg_latency_ms:.1f}ms | p50 {latest_benchmark.p50_ms:.1f}ms | p90 {latest_benchmark.p90_ms:.1f}ms | p99 {latest_benchmark.p99_ms:.1f}ms\n"
                )
                if latest_benchmark.ai_recommendation:
                    benchmark_context += f"- สรุปผล AI Recommendation ล่าสุด: {latest_benchmark.ai_recommendation[:700]}...\n"
            except Exception as ex:
                print(f"[!] Error building benchmark_context for chat: {ex}")

        # 5.2 Fetch live telemetry metrics & live DB connection probes
        live_telemetry_context = fetch_live_system_telemetry(db=db)

        # 6. Define System Prompt with strict Telemetry Overrides
        system_prompt = (
            "CRITICAL INSTRUCTION: You possess FULL direct network monitoring and database probing capabilities integrated into your backend engine.\n"
            "The backend Python engine HAS ALREADY PROBED and TESTED the live network connections to WMS-DB and TMS-DB right now at this exact second.\n"
            "NEVER EVER OUTPUT PRE-TRAINED DISCLAIMERS LIKE 'ผมไม่มีความสามารถในการเชื่อมต่อเข้า Server หรือ Database ของคุณได้โดยตรง' or 'ในฐานะ AI ไม่สามารถเชื่อมต่อได้'. THAT DISCLAIMER IS STRICTLY FORBIDDEN AND FALSE.\n"
            "INSTANTLY ANSWER THE USER WITH THE EXACT LIVE DB PROBE TELEMETRY RESULTS PROVIDED BELOW:\n"
            + live_telemetry_context
            + "\n\n"
            "คำสั่งเพิ่มเติม: หากพบว่าฐานข้อมูลตัวใด (เช่น TMS-DB) เชื่อมต่อไม่ได้ ให้แจ้งผลความล้มเหลวสดที่ตรวจพบ (เช่น FATAL: password authentication failed บน Port 6432) และแนะนำแนวทางแก้ไข (เช่น เปลี่ยน Port เป็น 5432 ในหน้า Settings หรือเพิ่ม user ใน userlist.txt ของ PgBouncer) ทันทีอย่างสุภาพและมืออาชีพ\n\n"
            "บทบาทของคุณ: คุณคือผู้ช่วยวิศวกรระบบและผู้ดูแลระบบฐานข้อมูลอาวุโส (Senior DevOps & DBA) "
            "หน้าที่ของคุณคือช่วยเหลือตอบคำถามเชิงเทคนิคเกี่ยวกับการจูน PostgreSQL, PgBouncer, Nginx, Linux, และแอป Spring Boot "
            "ให้คำแนะนำที่ชัดเจน ปลอดภัย และนำไปปฏิบัติจริงได้ตามสถาปัตยกรรม WMS/TMS ของโครงการ"
            + report_context
            + benchmark_context
        )

        # 6. Query AI Model
        ai_reply = call_chat_ai(
            provider=setting.ai_provider,
            host_url=setting.ai_host_url,
            model_name=setting.ai_model_name,
            messages_history=messages_history,
            system_prompt=system_prompt
        )

    # 7. Save assistant reply to database
    assistant_message = ChatMessage(role="assistant", content=ai_reply)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return assistant_message

@app.delete("/api/chat/messages")
def clear_chat_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ล้างประวัติบทสนทนาทั้งหมดในระบบ (เริ่มคุยหัวข้อใหม่)
    """
    db.query(ChatMessage).delete()
    db.commit()
    return {"status": "success", "message": "ล้างประวัติการสนทนาเรียบร้อยแล้ว"}


# --- Proactive Health Monitoring Routes ---

@app.get("/api/health/live", response_model=Optional[HealthEventResponse])
def get_live_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the most recent proactive HealthEvent snapshot.
    Used by frontend Dashboard Health Status Banner.
    """
    latest = db.query(HealthEvent).order_by(HealthEvent.timestamp.desc()).first()
    return latest

@app.get("/api/health/history", response_model=List[HealthEventResponse])
def get_health_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns recent health event history.
    """
    events = db.query(HealthEvent).order_by(HealthEvent.timestamp.desc()).limit(limit).all()
    return events

@app.post("/api/health/trigger")
def trigger_manual_proactive_check(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually triggers a proactive health check immediately in the background.
    """
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Settings not configured")

    def _run():
        db_session = SessionLocal()
        try:
            run_proactive_health_check(setting, db_session, REDIS_URL)
        finally:
            db_session.close()

    background_tasks.add_task(_run)
    return {"status": "Proactive health check scheduled"}


@app.post("/api/health/diagnose/{event_id}", response_model=HealthEventResponse)
def trigger_event_ai_diagnosis(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Triggers AI Root Cause Diagnosis on-demand for a specific HealthEvent.
    """
    event = db.query(HealthEvent).filter(HealthEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="HealthEvent not found")

    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Settings not configured")

    alerts = json.loads(event.alerts_json) if event.alerts_json else []
    metrics = json.loads(event.metrics_json) if event.metrics_json else {}

    container_metrics = metrics.get("containers", {})
    pgb_metrics = metrics.get("pgbouncer", {})
    springboot_metrics = metrics.get("springboot", {})
    db_health = metrics.get("db_health", [])
    error_count = metrics.get("loki_error_count_5m", 0)

    from .proactive_monitor import _call_ai_diagnosis
    ai_diagnosis = _call_ai_diagnosis(
        setting, alerts, container_metrics, pgb_metrics, db_health, error_count, springboot_metrics
    )

    event.ai_diagnosis = ai_diagnosis
    db.commit()
    db.refresh(event)
    return event


class TerminatePidRequest(BaseModel):
    db_label: str
    pid: int
    force: bool = False  # True: pg_terminate_backend (kill), False: pg_cancel_backend (cancel query)


class LiveAITroubleshootRequest(BaseModel):
    db_label: str
    pid: Optional[int] = None
    query: Optional[str] = None
    lock_info: Optional[Dict[str, Any]] = None


def collect_full_realtime_db_snapshot(db: Session):
    """
    Collects a rich real-time diagnostic snapshot across all PostgreSQL databases:
    - Lock tree & blocker correlation graph
    - Active & running slow queries with wait events
    - Connection state breakdown (active, idle, idle in transaction)
    - PgBouncer client waiting queues and active connections
    - Spring Boot HikariCP pool and JVM metrics
    """
    import psycopg2
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting or not setting.db_connections_json:
        return {"error": "No database connections configured", "databases": []}

    try:
        db_conns = json.loads(setting.db_connections_json)
    except Exception:
        db_conns = []

    results = []
    total_active = 0
    total_locks = 0

    for conn_info in db_conns:
        label = conn_info.get("label", conn_info.get("host", "DB"))
        host = conn_info.get("host")
        port = int(conn_info.get("port", 5432))
        dbname = conn_info.get("dbname")
        user = conn_info.get("user")
        password = conn_info.get("password")

        if not all([host, dbname, user, password]):
            continue

        db_entry = {
            "label": label,
            "host": host,
            "port": port,
            "dbname": dbname,
            "connected": False,
            "error": None,
            "conn_active": 0,
            "conn_idle": 0,
            "conn_idle_in_tx": 0,
            "conn_max": 0,
            "conn_pct": 0.0,
            "active_queries": [],
            "lock_tree": [],
            "wait_events": [],
            "disk_io_waits": 0
        }

        conn = None
        try:
            conn = psycopg2.connect(
                host=host, port=port, dbname=dbname,
                user=user, password=password, connect_timeout=3
            )
            cur = conn.cursor()
            db_entry["connected"] = True

            # 1. Connection states breakdown
            try:
                cur.execute("""
                    SELECT state, count(*) 
                    FROM pg_stat_activity 
                    WHERE pid != pg_backend_pid()
                    GROUP BY state
                """)
                for st, cnt in cur.fetchall():
                    if st == 'active':
                        db_entry["conn_active"] = cnt
                    elif st == 'idle':
                        db_entry["conn_idle"] = cnt
                    elif st == 'idle in transaction':
                        db_entry["conn_idle_in_tx"] = cnt
            except Exception:
                conn.rollback()

            try:
                cur.execute("SHOW max_connections")
                db_entry["conn_max"] = int(cur.fetchone()[0] or 100)
                db_entry["conn_pct"] = round((db_entry["conn_active"] / db_entry["conn_max"] * 100) if db_entry["conn_max"] > 0 else 0.0, 1)
                total_active += db_entry["conn_active"]
            except Exception:
                conn.rollback()

            # 2. Lock Tree / Blocking Sessions Graph (Deadlocks & Lock Contention)
            try:
                cur.execute("""
                    SELECT
                        blocked_locks.pid AS blocked_pid,
                        blocked_activity.usename AS blocked_user,
                        blocked_activity.client_addr::text AS blocked_client,
                        ROUND(EXTRACT(epoch FROM (now() - blocked_activity.query_start)))::int AS blocked_duration_sec,
                        SUBSTRING(blocked_activity.query FROM 1 FOR 300) AS blocked_statement,
                        blocked_activity.state AS blocked_state,
                        COALESCE(blocked_activity.wait_event_type, 'Lock') AS blocked_wait_type,
                        COALESCE(blocked_activity.wait_event, 'transactionid') AS blocked_wait_event,
                        blocking_locks.pid AS blocking_pid,
                        blocking_activity.usename AS blocking_user,
                        blocking_activity.client_addr::text AS blocking_client,
                        ROUND(EXTRACT(epoch FROM (now() - blocking_activity.query_start)))::int AS blocking_duration_sec,
                        SUBSTRING(blocking_activity.query FROM 1 FOR 300) AS blocking_statement,
                        blocking_activity.state AS blocking_state,
                        blocking_locks.mode AS lock_mode,
                        blocking_locks.locktype AS lock_type
                    FROM pg_catalog.pg_locks blocked_locks
                    JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
                    JOIN pg_catalog.pg_locks blocking_locks 
                        ON blocking_locks.locktype = blocked_locks.locktype
                        AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
                        AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
                        AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
                        AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
                        AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
                        AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
                        AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
                        AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
                        AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
                        AND blocking_locks.pid != blocked_locks.pid
                    JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
                    WHERE NOT blocked_locks.granted
                    ORDER BY blocked_duration_sec DESC LIMIT 20;
                """)
                for r in cur.fetchall():
                    db_entry["lock_tree"].append({
                        "blocked_pid": r[0],
                        "blocked_user": r[1],
                        "blocked_client": r[2],
                        "blocked_duration_sec": r[3] or 0,
                        "blocked_statement": r[4],
                        "blocked_state": r[5],
                        "blocked_wait_type": r[6],
                        "blocked_wait_event": r[7],
                        "blocking_pid": r[8],
                        "blocking_user": r[9],
                        "blocking_client": r[10],
                        "blocking_duration_sec": r[11] or 0,
                        "blocking_statement": r[12],
                        "blocking_state": r[13],
                        "lock_mode": r[14],
                        "lock_type": r[15]
                    })
                total_locks += len(db_entry["lock_tree"])
            except Exception:
                conn.rollback()

            # 3. Active Queries
            try:
                cur.execute("""
                    SELECT pid, usename, client_addr::text, state,
                           COALESCE(wait_event_type, 'Executing/CPU') AS wait_type,
                           COALESCE(wait_event, 'Active') AS wait_ev,
                           ROUND(EXTRACT(epoch FROM (now() - query_start)))::int AS dur,
                           ROUND(EXTRACT(epoch FROM (now() - state_change)))::int AS state_dur,
                           SUBSTRING(query FROM 1 FOR 400) AS q_text,
                           pg_blocking_pids(pid) AS blocking_pids
                    FROM pg_stat_activity
                    WHERE state != 'idle' 
                      AND pid != pg_backend_pid()
                      AND backend_type != 'walsender'
                      AND query NOT ILIKE 'START_REPLICATION%'
                      AND query NOT ILIKE 'autovacuum:%'
                      AND query_start IS NOT NULL
                    ORDER BY dur DESC LIMIT 25
                """)
                for row in cur.fetchall():
                    pid, usename, client, st, wtype, wev, dur, sdur, qtxt, blocking = row
                    db_entry["active_queries"].append({
                        "pid": pid,
                        "usename": usename,
                        "client_addr": client,
                        "state": st,
                        "wait_event_type": wtype,
                        "wait_event": wev,
                        "duration_sec": dur or 0,
                        "state_duration_sec": sdur or 0,
                        "query": qtxt,
                        "blocking_pids": [int(p) for p in (blocking or [])]
                    })
            except Exception:
                conn.rollback()

            # 4. Wait Event Breakdown
            try:
                cur.execute("""
                    SELECT COALESCE(wait_event_type, 'CPU / Executing') AS wtype,
                           COALESCE(wait_event, 'Active') AS wev,
                           count(*) AS cnt
                    FROM pg_stat_activity
                    WHERE state != 'idle' AND pid != pg_backend_pid() AND backend_type != 'walsender'
                    GROUP BY wait_event_type, wait_event
                    ORDER BY count(*) DESC LIMIT 8
                """)
                for wrow in cur.fetchall():
                    wt, we, wc = wrow
                    db_entry["wait_events"].append({"wait_type": wt, "wait_event": we, "count": wc})
                    if wt == 'IO':
                        db_entry["disk_io_waits"] += wc
            except Exception:
                conn.rollback()

            cur.close()
            conn.close()
        except Exception as e:
            db_entry["error"] = str(e).strip().replace('\n', ' ')
            if conn:
                try: conn.close()
                except: pass

        results.append(db_entry)

    from .proactive_monitor import _fetch_pgbouncer_metrics, _fetch_container_metrics, _fetch_springboot_actuator_metrics
    projects = json.loads(setting.loki_projects) if setting.loki_projects else []
    pgb_metrics = _fetch_pgbouncer_metrics(setting.prometheus_ip, setting.prometheus_port, projects)
    container_metrics = _fetch_container_metrics(setting.prometheus_ip, setting.prometheus_port, projects)
    springboot_metrics = _fetch_springboot_actuator_metrics(setting.prometheus_ip, setting.prometheus_port, projects)

    return {
        "timestamp": datetime.now().isoformat(),
        "total_active_connections": total_active,
        "total_lock_conflicts": total_locks,
        "databases": results,
        "pgbouncer": pgb_metrics,
        "containers": container_metrics,
        "springboot": springboot_metrics
    }


@app.get("/api/db/snapshot-realtime")
def get_db_snapshot_realtime(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns an instant comprehensive snapshot of all PostgreSQL databases:
    Lock graph, active slow queries, wait events, PgBouncer, and HikariCP queues.
    """
    return collect_full_realtime_db_snapshot(db)


@app.get("/api/db/stream-realtime")
async def stream_db_realtime(
    token: Optional[str] = Query(None)
):
    """
    Server-Sent Events (SSE) stream pushing live PostgreSQL status,
    active queries, and lock tree updates every 2 seconds.
    """
    # Verify token
    if token:
        try:
            from jose import jwt
            from .auth import SECRET_KEY, ALGORITHM
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

    async def event_generator():
        while True:
            db = SessionLocal()
            try:
                data = collect_full_realtime_db_snapshot(db)
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                db.close()
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/db/terminate-pid")
def terminate_db_pid(
    req: TerminatePidRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Safely terminates or cancels a blocking / long-running query PID on the selected database.
    """
    import psycopg2
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting or not setting.db_connections_json:
        raise HTTPException(status_code=400, detail="No database connections configured")

    db_conns = json.loads(setting.db_connections_json)
    target_conn = next((c for c in db_conns if c.get("label") == req.db_label or c.get("host") == req.db_label), None)
    if not target_conn:
        raise HTTPException(status_code=404, detail=f"Database '{req.db_label}' not found")

    host = target_conn.get("host")
    port = int(target_conn.get("port", 5432))
    dbname = target_conn.get("dbname")
    user = target_conn.get("user")
    password = target_conn.get("password")

    func_name = "pg_terminate_backend" if req.force else "pg_cancel_backend"
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=4)
        cur = conn.cursor()
        cur.execute(f"SELECT {func_name}(%s)", (req.pid,))
        result = cur.fetchone()[0]
        cur.close()
        conn.close()
        action_name = "Terminated (Killed)" if req.force else "Cancelled"
        return {
            "status": "success" if result else "not_found",
            "message": f"Successfully {action_name} PID {req.pid} on {req.db_label}",
            "pid": req.pid,
            "db_label": req.db_label
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute {func_name}({req.pid}): {str(e)}")


@app.post("/api/db/ai-troubleshoot-realtime")
def ai_troubleshoot_realtime(
    req: LiveAITroubleshootRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Instant AI Root Cause Diagnosis & Actionable Remediation for an active Lock or Slow Query.
    """
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        raise HTTPException(status_code=400, detail="Settings not configured")

    from .analyzer import call_chat_ai

    system_prompt = (
        "คุณคือ Senior Database Administrator (DBA) และ PostgreSQL Troubleshooting Expert "
        "หน้าที่ของคุณคือรับข้อมูลคิวรีที่กำลังค้าง, คิวรีที่ติด Lock, หรือ Blocker Session ณ วินาทีนี้ "
        "และให้คำวินิจฉัย Root Cause พร้อมคำสั่ง SQL / Linux Bash สำหรับปลดล็อคและแก้ไขทันทีใน 1-3 นาที\n\n"
        "โครงสร้างคำตอบ:\n"
        "1. 🚨 **Root Cause Diagnosis**: ทำไมคิวรีนี้ถึงช้า หรือ ทำไมถึงเกิด Lock Contention\n"
        "2. ⚡ **Immediate Mitigation**: คำสั่ง SQL/Bash ที่ต้องทำทันที (เช่น สั่ง Kill PID หรือ Cancel Transaction)\n"
        "3. 🛠️ **Permanent Solution**: แนะนำ Index, Tuning Parameters (เช่น idle_in_transaction_session_timeout, lock_timeout), หรือการแก้โค้ด ORM/Spring Boot\n"
        "ห้ามใช้ HTML Tags ให้ใช้ Markdown ล้วน"
    )

    context_lines = [f"ฐานข้อมูลเป้าหมาย: {req.db_label}"]
    if req.pid:
        context_lines.append(f"Target PID: {req.pid}")
    if req.query:
        context_lines.append(f"SQL Statement: {req.query}")
    if req.lock_info:
        context_lines.append(f"Lock Information: {json.dumps(req.lock_info, ensure_ascii=False)}")

    user_prompt = "กรุณาวิเคราะห์ปัญหาและแนะนำวิธีแก้ไข Real-time สำหรับสถานการณ์ต่อไปนี้:\n\n" + "\n".join(context_lines)

    ai_reply = call_chat_ai(
        provider=setting.ai_provider,
        host_url=setting.ai_host_url,
        model_name=setting.ai_model_name,
        messages_history=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt
    )

    return {
        "status": "success",
        "db_label": req.db_label,
        "pid": req.pid,
        "ai_recommendation": ai_reply
    }


@app.get("/api/db/diagnose-realtime")
def diagnose_postgresql_realtime(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Performs on-demand real-time live diagnostic inspection and root-cause troubleshooting
    across all configured PostgreSQL databases and PgBouncer pools.
    """
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting or not setting.db_connections_json:
        raise HTTPException(status_code=400, detail="No database connections configured in Settings")

    from .proactive_monitor import (
        _fetch_db_health, _call_ai_diagnosis, _fetch_container_metrics,
        _fetch_pgbouncer_metrics, _fetch_springboot_actuator_metrics
    )

    projects = json.loads(setting.loki_projects) if setting.loki_projects else []
    db_health = _fetch_db_health(setting.db_connections_json)
    container_metrics = _fetch_container_metrics(setting.prometheus_ip, setting.prometheus_port, projects)
    pgb_metrics = _fetch_pgbouncer_metrics(setting.prometheus_ip, setting.prometheus_port, projects)
    springboot_metrics = _fetch_springboot_actuator_metrics(setting.prometheus_ip, setting.prometheus_port, projects)

    anomalies = []
    for entry in db_health:
        if entry.get("error"):
            anomalies.append(f"Connection Failed: {entry['error']}")
        if entry.get("conn_pct", 0) > 80:
            anomalies.append(f"High Connection Load on {entry['label']}: {entry['conn_active']}/{entry['conn_max']} ({entry['conn_pct']:.0f}%)")
        for q in entry.get("long_queries", []):
            if q.get("duration_sec", 0) > 5:
                anomalies.append(f"Long Query on {entry['label']} (PID {q['pid']}, {q['duration_sec']}s): {q['query'][:80]}")
            if q.get("blocking_pids"):
                anomalies.append(f"Lock Contention on {entry['label']}: PID {q['pid']} blocked by PID {q['blocking_pids']}")

    ai_troubleshooting = None
    if anomalies:
        ai_troubleshooting = _call_ai_diagnosis(
            setting, anomalies, container_metrics, pgb_metrics, db_health, 0, springboot_metrics
        )

    return {
        "timestamp": datetime.now().isoformat(),
        "databases": db_health,
        "pgbouncer": pgb_metrics,
        "anomalies_detected": anomalies,
        "ai_root_cause_troubleshooting": ai_troubleshooting
    }


# ─────────────────────────────────────────────────
# Benchmark API Endpoints
# ─────────────────────────────────────────────────
from .schemas import BenchmarkStartRequest, BenchmarkReportResponse
from .benchmark_engine import benchmark_engine

@app.post("/api/benchmark/start")
def start_benchmark(
    req: BenchmarkStartRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Starts a new asynchronous HTTP or PostgreSQL Benchmark Load/Stress Test.
    """
    if benchmark_engine.is_running:
        raise HTTPException(status_code=400, detail="A benchmark test is already running. Please wait or stop it first.")

    setting = db.query(Setting).filter(Setting.id == 1).first()

    if req.mode == "http":
        if not req.target_url:
            raise HTTPException(status_code=400, detail="target_url is required for HTTP benchmark")
        background_tasks.add_task(
            benchmark_engine.run_http_benchmark,
            req.name,
            req.target_url,
            req.http_method or "GET",
            req.headers_json,
            req.payload_json,
            req.concurrent_users,
            req.duration_seconds,
            setting,
            db
        )
    elif req.mode == "postgres":
        if not req.sql_query:
            raise HTTPException(status_code=400, detail="sql_query is required for PostgreSQL benchmark")

        db_conns = json.loads(setting.db_connections_json) if setting and setting.db_connections_json else []
        selected_conn = None
        for c in db_conns:
            if c.get("label") == req.db_label or c.get("host") == req.db_label:
                selected_conn = c
                break

        if not selected_conn and db_conns:
            selected_conn = db_conns[0]

        if not selected_conn:
            raise HTTPException(status_code=400, detail="No DB Connections configured in Settings")

        background_tasks.add_task(
            benchmark_engine.run_postgres_benchmark,
            req.name,
            selected_conn,
            req.sql_query,
            req.concurrent_users,
            req.duration_seconds,
            setting,
            db
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid benchmark mode. Use 'http' or 'postgres'")

    return {"status": "Benchmark test started", "mode": req.mode}


@app.get("/api/benchmark/live")
def get_live_benchmark_status(current_user: User = Depends(get_current_user)):
    """Returns real-time streaming status of executing benchmark."""
    return benchmark_engine.get_live_status()


@app.post("/api/benchmark/stop")
def stop_benchmark(current_user: User = Depends(get_current_user)):
    """Stops currently executing benchmark test."""
    benchmark_engine.stop()
    return {"status": "Stop signal sent"}


@app.get("/api/benchmark/reports", response_model=List[BenchmarkReportResponse])
def get_benchmark_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists historical benchmark reports."""
    from .models import BenchmarkReport
    return db.query(BenchmarkReport).order_by(BenchmarkReport.id.desc()).all()


@app.get("/api/benchmark/reports/{report_id}", response_model=BenchmarkReportResponse)
def get_benchmark_report_detail(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetches details of a specific benchmark report."""
    from .models import BenchmarkReport
    report = db.query(BenchmarkReport).filter(BenchmarkReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="BenchmarkReport not found")
    return report


@app.delete("/api/benchmark/reports/{report_id}")
def delete_benchmark_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deletes a benchmark report."""
    from .models import BenchmarkReport
    report = db.query(BenchmarkReport).filter(BenchmarkReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="BenchmarkReport not found")
    db.delete(report)
    db.commit()
    return {"status": "BenchmarkReport deleted"}


