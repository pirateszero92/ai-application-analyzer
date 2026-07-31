import os
import threading
import json
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import and_
from sqlalchemy.orm import Session
from typing import List, Optional

from .database import SessionLocal, engine, Base, get_db
from .models import User, Setting, Report, DailySummary, ChatMessage, HealthEvent
from .schemas import (
    UserLogin, Token, UserChangePassword, UserResponse,
    SettingResponse, SettingUpdate, ReportResponse, ReportDetailResponse,
    DailySummaryResponse, ChatMessageCreate, ChatMessageResponse, HealthEventResponse
)
from .auth import (
    verify_password, get_password_hash, create_access_token, get_current_user
)
from .scheduler import start_scheduler, stop_scheduler, REDIS_URL
from .analyzer import run_analysis_job, generate_daily_ai_summary, call_chat_ai
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
        # 4. Build context messages (history + new user message)
        messages_history = [{"role": r.role, "content": r.content} for r in history_records]
        messages_history.append({"role": "user", "content": chat_msg.content})

        # 5. Fetch the latest analysis report as context-aware data
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

        # 5. Define System Prompt
        system_prompt = (
            "คุณคือผู้ช่วยวิศวกรระบบและผู้ดูแลระบบฐานข้อมูลอาวุโส (Senior DevOps & DBA) "
            "หน้าที่ของคุณคือช่วยเหลือตอบคำถามเชิงเทคนิคเกี่ยวกับการจูน PostgreSQL, PgBouncer, Nginx, Linux, และแอป Spring Boot "
            "ให้คำแนะนำที่ชัดเจน ปลอดภัย และนำไปปฏิบัติจริงได้ตามสถาปัตยกรรม WMS/TMS ของโครงการ"
            + report_context
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


