import os
import time
import json
import threading
from datetime import datetime, timedelta
import redis
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Setting, Report
from .analyzer import run_analysis_job
from .proactive_monitor import run_proactive_health_check

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Global variables to manage the scheduler thread
_scheduler_thread = None
_stop_event = threading.Event()

def get_redis_client():
    try:
        return redis.Redis.from_url(REDIS_URL, socket_timeout=5)
    except Exception as e:
        print(f"[!] Failed to connect to Redis at {REDIS_URL}: {str(e)}")
        return None

def check_and_trigger_proactive_check():
    db = SessionLocal()
    r = get_redis_client()
    if not r:
        db.close()
        return

    try:
        setting = db.query(Setting).filter(Setting.id == 1).first()
        if not setting or not getattr(setting, "proactive_enabled", True):
            db.close()
            return

        interval_minutes = getattr(setting, "proactive_interval_minutes", 2) or 2
        interval_seconds = interval_minutes * 60
        now = time.time()

        last_run = r.get("ai_analyzer:last_proactive_run_timestamp")
        if last_run:
            elapsed = now - float(last_run)
            if elapsed < interval_seconds:
                db.close()
                return

        lock_acquired = r.set("ai_analyzer:proactive_lock", "locked", ex=120, nx=True)
        if not lock_acquired:
            db.close()
            return

        try:
            run_proactive_health_check(setting, db, REDIS_URL)
            r.set("ai_analyzer:last_proactive_run_timestamp", str(time.time()))
        finally:
            r.delete("ai_analyzer:proactive_lock")

    except Exception as e:
        print(f"[!] Proactive check scheduler error: {str(e)}")
        if r:
            r.delete("ai_analyzer:proactive_lock")
    finally:
        db.close()

def check_and_trigger_analysis():
    db = SessionLocal()
    r = get_redis_client()
    if not r:
        db.close()
        return

    try:
        # Fetch setting (ID=1)
        setting = db.query(Setting).filter(Setting.id == 1).first()
        if not setting or not setting.is_active:
            db.close()
            return

        interval_seconds = setting.interval_minutes * 60
        now = time.time()
        
        # Check last run timestamp from Redis
        last_run = r.get("ai_analyzer:last_run_timestamp")
        if last_run:
            elapsed = now - float(last_run)
            if elapsed < interval_seconds:
                # Not yet time to run
                db.close()
                return

        # Attempt to acquire a lock in Redis to avoid concurrent runs across instances/pods
        # Lock expires in 10 minutes (600s) to avoid deadlocks
        lock_acquired = r.set("ai_analyzer:job_lock", "locked", ex=600, nx=True)
        if not lock_acquired:
            # Another instance has the lock, or is running the job
            db.close()
            return

        print("[*] Scheduler: Triggering periodic log analysis job...")
        
        # 1. Create a Report placeholder
        report = Report(status="running")
        db.add(report)
        db.commit()
        db.refresh(report)
        report_id = report.id
        
        try:
            # 2. Run analysis
            run_analysis_job(db, report_id)
            
            # 3. Update last run timestamp in Redis only on success
            r.set("ai_analyzer:last_run_timestamp", str(time.time()))
        finally:
            # 4. Always release lock regardless of success or failure
            r.delete("ai_analyzer:job_lock")
        
    except Exception as e:
        print(f"[!] Scheduler error: {str(e)}")
        if r:
            r.delete("ai_analyzer:job_lock")
    finally:
        db.close()

def _scheduler_loop():
    print("[*] Background scheduler thread started.")
    # Wait 10 seconds on startup before checking to allow DB/Minio/Loki to boot up
    time.sleep(10)
    
    while not _stop_event.is_set():
        try:
            check_and_trigger_proactive_check()
            check_and_trigger_analysis()
        except Exception as e:
            print(f"[!] Error in scheduler loop: {str(e)}")
        # Sleep for 15 seconds before next loop check
        for _ in range(15):
            if _stop_event.is_set():
                break
            time.sleep(1)

def start_scheduler():
    global _scheduler_thread
    if _scheduler_thread is None:
        _stop_event.clear()
        _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
        _scheduler_thread.start()

def stop_scheduler():
    global _scheduler_thread
    if _scheduler_thread is not None:
        _stop_event.set()
        _scheduler_thread.join()
        _scheduler_thread = None
        print("[*] Background scheduler thread stopped.")

