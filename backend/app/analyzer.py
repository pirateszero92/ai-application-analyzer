import os
import requests
import json
import re
import time
import urllib3
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import Setting, Report
from .storage import upload_report_archive

# Disable SSL warnings if verify is False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurable SSL Verification for PMM requests
PMM_VERIFY_SSL = os.getenv("PMM_VERIFY_SSL", "False").lower() in ("true", "1")

# Whitelist pattern for Loki project names to prevent LogQL injection
_SAFE_PROJECT_NAME = re.compile(r'^[a-zA-Z0-9_-]+$')

def fetch_loki_logs(loki_ip: str, projects: list, lookback_minutes: int = 15) -> str:
    loki_url = f"http://{loki_ip}:3100/loki/api/v1/query_range"
    print(f"[*] Fetching logs from Loki ({loki_ip}) for projects: {projects} (lookback: {lookback_minutes} mins)...")
    
    if not projects:
        return ""

    # Sanitize project names to prevent LogQL injection
    safe_projects = [p for p in projects if _SAFE_PROJECT_NAME.match(str(p))]
    if not safe_projects:
        print("[!] No valid project names after sanitization. Skipping Loki query.")
        return ""

    projects_regex = "|".join(safe_projects)
    logql_query = f'{{project=~"{projects_regex}", environment="production"}}'
    
    now_ns = int(time.time() * 1000000000)
    start_ns = now_ns - (lookback_minutes * 60 * 1000000000)
    
    params = {
        'query': logql_query,
        'limit': 1000,
        'start': start_ns,
        'end': now_ns
    }
    
    try:
        response = requests.get(loki_url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = data.get('data', {}).get('result', [])
            
            critical_logs = []
            for item in results:
                metric = item.get('stream', item.get('metric', {}))
                project_label = metric.get('project', 'unknown')
                
                for val in item.get('values', []):
                    log_text = val[1]
                    # Filter for latency or errors
                    if any(x in log_text.lower() for x in ["error", "warn", "status=5", "totaltime:"]):
                        formatted_log = f"[{project_label}] {log_text.strip()}"
                        critical_logs.append(formatted_log)
                        
            return "\n".join(critical_logs[:80])
        else:
            print(f"[!] Loki error status: {response.status_code}")
            return f"Error querying Loki: Status {response.status_code}"
    except Exception as e:
        print(f"[!] Loki connection failed: {str(e)}")
        return ""

def fetch_pmm_slow_queries(pmm_ip: str, pmm_port: str, pmm_user: str, pmm_pass: str, db_filters: list, lookback_minutes: int = 15) -> str:
    pmm_url = f"https://{pmm_ip}:{pmm_port}/v1/qan/metrics:getReport"
    print(f"[*] Fetching slow queries from PMM ({pmm_ip}:{pmm_port}) for databases: {db_filters} (lookback: {lookback_minutes} mins)...")
    
    now = datetime.utcnow()
    start_time = now - timedelta(minutes=lookback_minutes)
    start_iso = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_iso = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    payload = {
        "columns": ["load", "num_queries", "query_time"],
        "group_by": "queryid",
        "limit": 10,
        "period_start_from": start_iso,
        "period_start_to": end_iso,
        "labels": [
            {"key": "database", "value": db_filters}
        ],
        "order_by": "-query_time"
    }
    
    try:
        response = requests.post(pmm_url, json=payload, auth=(pmm_user, pmm_pass), verify=PMM_VERIFY_SSL, timeout=15)
        if response.status_code == 200:
            data = response.json()
            rows = data.get("rows", [])
            
            slow_queries_text = ""
            idx = 1
            for row in rows:
                fingerprint = row.get("fingerprint", "")
                if fingerprint == "TOTAL" or not fingerprint:
                    continue
                
                metrics = row.get("metrics", {})
                q_time_stats = metrics.get("query_time", {}).get("stats", {})
                
                avg_time = q_time_stats.get("avg", 0)
                cnt = q_time_stats.get("cnt", 0)
                sum_time = q_time_stats.get("sum", 0)
                db_name = row.get("database", "unknown")
                
                slow_queries_text += f"\n[{idx}] DB: {db_name} | Avg: {avg_time:.4f}s | Calls: {cnt} | Total: {sum_time:.4f}s\nQuery: {fingerprint}\n"
                idx += 1
                
            return slow_queries_text if slow_queries_text else "ไม่พบ Slow Queries ในฐานข้อมูลในช่วงเวลานี้"
        else:
            return f"Error querying PMM: Status {response.status_code} - {response.text}"
    except Exception as e:
        return f"Failed to connect to PMM: {str(e)}"

def fetch_prometheus_metrics(prometheus_ip: str, prometheus_port: str, projects: list, lookback_minutes: int = 15) -> str:
    print(f"[*] Fetching deep infrastructure metrics from Prometheus ({prometheus_ip}:{prometheus_port}) for projects: {projects}...")
    if not projects:
        return ""
        
    end_ts = int(time.time())
    start_ts = end_ts - (lookback_minutes * 60)
    
    range_url = f"http://{prometheus_ip}:{prometheus_port}/api/v1/query_range"
    
    # Build job patterns based on projects (e.g. wms-prod-containers, tms-prod-containers)
    container_jobs = "|".join([f"{p}-prod-containers" for p in projects])
    pgbouncer_jobs = "|".join([f"{p}-pgbouncer-prod" for p in projects])
    node_jobs = "|".join([f"node-{p}-service-prod" for p in projects])
    
    container_cpu_q = f'sum(rate(container_cpu_usage_seconds_total{{job=~"{container_jobs}", container!="POD", container!=""}}[5m])) by (container) * 100'
    container_mem_q = f'container_memory_working_set_bytes{{job=~"{container_jobs}", container!="POD", container!=""}}'
    
    pgb_waiting_q = f'sum(pgbouncer_pools_client_waiting_connections{{job=~"{pgbouncer_jobs}"}}) by (database)'
    pgb_active_q = f'sum(pgbouncer_pools_client_active_connections{{job=~"{pgbouncer_jobs}"}}) by (database)'
    
    node_cpu_q = f'(1 - avg(rate(node_cpu_seconds_total{{job=~"{node_jobs}", mode="idle"}}[5m])) by (job)) * 100'
    node_mem_q = f'(1 - node_memory_MemAvailable_bytes{{job=~"{node_jobs}"}} / node_memory_MemTotal_bytes{{job=~"{node_jobs}"}}) * 100'
    
    summary_lines = []
    
    # 1. Query Containers
    metrics_summary = {}
    try:
        # CPU
        res = requests.get(range_url, params={'query': container_cpu_q, 'start': start_ts, 'end': end_ts, 'step': '2m'}, timeout=10)
        if res.status_code == 200:
            for item in res.json().get('data', {}).get('result', []):
                container_name = item.get('metric', {}).get('container', 'unknown')
                values = [float(v[1]) for v in item.get('values', []) if v[1] not in ('NaN', '+Inf', '-Inf')]
                if values:
                    metrics_summary[container_name] = {
                        'avg_cpu': sum(values) / len(values),
                        'max_cpu': max(values),
                        'avg_mem': 0,
                        'max_mem': 0
                    }
        # Memory
        res = requests.get(range_url, params={'query': container_mem_q, 'start': start_ts, 'end': end_ts, 'step': '2m'}, timeout=10)
        if res.status_code == 200:
            for item in res.json().get('data', {}).get('result', []):
                container_name = item.get('metric', {}).get('container', 'unknown')
                values = [float(v[1]) / (1024 * 1024) for v in item.get('values', []) if v[1] not in ('NaN', '+Inf', '-Inf')]
                if values:
                    if container_name not in metrics_summary:
                        metrics_summary[container_name] = {'avg_cpu': 0, 'max_cpu': 0, 'avg_mem': 0, 'max_mem': 0}
                    metrics_summary[container_name]['avg_mem'] = sum(values) / len(values)
                    metrics_summary[container_name]['max_mem'] = max(values)
    except Exception as e:
        print(f"[!] Prometheus container queries failed: {str(e)}")
        
    if metrics_summary:
        summary_lines.append("=== [1] cAdvisor Container Resource Metrics ===")
        idx = 1
        for name, m in metrics_summary.items():
            summary_lines.append(
                f"[{idx}] Container: {name}\n"
                f"   - CPU Usage: เฉลี่ย {m['avg_cpu']:.2f}% | สูงสุด {m['max_cpu']:.2f}%\n"
                f"   - Memory Usage: เฉลี่ย {m['avg_mem']:.2f} MB | สูงสุด {m['max_mem']:.2f} MB"
            )
            idx += 1
            
    # 2. Query PgBouncer
    pgb_summary = {}
    try:
        # Waiting
        res = requests.get(range_url, params={'query': pgb_waiting_q, 'start': start_ts, 'end': end_ts, 'step': '2m'}, timeout=10)
        if res.status_code == 200:
            for item in res.json().get('data', {}).get('result', []):
                db_name = item.get('metric', {}).get('database', 'unknown')
                values = [float(v[1]) for v in item.get('values', []) if v[1] not in ('NaN', '+Inf', '-Inf')]
                if values:
                    pgb_summary[db_name] = {'max_waiting': max(values), 'avg_active': 0, 'max_active': 0}
        # Active
        res = requests.get(range_url, params={'query': pgb_active_q, 'start': start_ts, 'end': end_ts, 'step': '2m'}, timeout=10)
        if res.status_code == 200:
            for item in res.json().get('data', {}).get('result', []):
                db_name = item.get('metric', {}).get('database', 'unknown')
                values = [float(v[1]) for v in item.get('values', []) if v[1] not in ('NaN', '+Inf', '-Inf')]
                if values:
                    if db_name not in pgb_summary:
                        pgb_summary[db_name] = {'max_waiting': 0, 'avg_active': 0, 'max_active': 0}
                    pgb_summary[db_name]['avg_active'] = sum(values) / len(values)
                    pgb_summary[db_name]['max_active'] = max(values)
    except Exception as e:
        print(f"[!] Prometheus PgBouncer queries failed: {str(e)}")
        
    if pgb_summary:
        summary_lines.append("\n=== [2] PgBouncer Connection Pool Metrics ===")
        idx = 1
        for db_name, p in pgb_summary.items():
            summary_lines.append(
                f"[{idx}] Database: {db_name}\n"
                f"   - Active Connections: เฉลี่ย {p['avg_active']:.1f} | สูงสุด {p['max_active']:.0f}\n"
                f"   - Clients Waiting: สูงสุด {p['max_waiting']:.0f} (หากค่า > 0 แสดงว่าคิวเต็มและเชื่อมต่อฐานข้อมูลล่าช้า)"
            )
            idx += 1
            
    # 3. Query Node Exporter
    node_summary = {}
    try:
        # CPU
        res = requests.get(range_url, params={'query': node_cpu_q, 'start': start_ts, 'end': end_ts, 'step': '2m'}, timeout=10)
        if res.status_code == 200:
            for item in res.json().get('data', {}).get('result', []):
                job_name = item.get('metric', {}).get('job', 'unknown')
                values = [float(v[1]) for v in item.get('values', []) if v[1] not in ('NaN', '+Inf', '-Inf')]
                if values:
                    node_summary[job_name] = {'avg_cpu': sum(values) / len(values), 'max_cpu': max(values), 'avg_mem': 0, 'max_mem': 0}
        # Memory
        res = requests.get(range_url, params={'query': node_mem_q, 'start': start_ts, 'end': end_ts, 'step': '2m'}, timeout=10)
        if res.status_code == 200:
            for item in res.json().get('data', {}).get('result', []):
                job_name = item.get('metric', {}).get('job', 'unknown')
                values = [float(v[1]) for v in item.get('values', []) if v[1] not in ('NaN', '+Inf', '-Inf')]
                if values:
                    if job_name not in node_summary:
                        node_summary[job_name] = {'avg_cpu': 0, 'max_cpu': 0, 'avg_mem': 0, 'max_mem': 0}
                    node_summary[job_name]['avg_mem'] = sum(values) / len(values)
                    node_summary[job_name]['max_mem'] = max(values)
    except Exception as e:
        print(f"[!] Prometheus Node Exporter queries failed: {str(e)}")
        
    if node_summary:
        summary_lines.append("\n=== [3] Virtual Machine Host Hardware Metrics ===")
        idx = 1
        for job_name, n in node_summary.items():
            if any(p in job_name.lower() for p in ['dev', 'staging', 'test']):
                continue
            summary_lines.append(
                f"[{idx}] Host Node Job: {job_name}\n"
                f"   - VM Host CPU Load: เฉลี่ย {n['avg_cpu']:.2f}% | สูงสุด {n['max_cpu']:.2f}%\n"
                f"   - VM Host Memory Load: เฉลี่ย {n['avg_mem']:.2f}% | สูงสุด {n['max_mem']:.2f}%"
            )
            idx += 1
            
    if not summary_lines:
        return "ไม่พบข้อมูล Deep Resource Metrics ในช่วงเวลานี้ หรือระบบไม่ได้เชื่อมโยง cAdvisor/PgBouncer/Node Exporter"
        
    return "\n".join(summary_lines)

def fetch_pmm_database_metrics(pmm_ip: str, pmm_port: str, pmm_user: str, pmm_password: str, db_filters: list) -> str:
    print(f"[*] Fetching database metrics from PMM VictoriaMetrics ({pmm_ip}:{pmm_port}) for databases: {db_filters}...")
    if not db_filters:
        return ""
        
    url = f"https://{pmm_ip}:{pmm_port}/prometheus/api/v1/query"
    from requests.auth import HTTPBasicAuth
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    auth = HTTPBasicAuth(pmm_user, pmm_password)
    summary_lines = []
    
    try:
        db_pattern = "|".join(db_filters)
        
        def run_q(query_str):
            try:
                res = requests.get(url, params={"query": query_str}, auth=auth, verify=PMM_VERIFY_SSL, timeout=10)
                if res.status_code == 200:
                    return res.json().get("data", {}).get("result", [])
            except Exception as e:
                print(f"[!] Error executing query {query_str}: {str(e)}")
            return []
            
        blks_hit = run_q(f"pg_stat_database_blks_hit{{datname=~'{db_pattern}'}}")
        blks_read = run_q(f"pg_stat_database_blks_read{{datname=~'{db_pattern}'}}")
        deadlocks_cum = run_q(f"pg_stat_database_deadlocks{{datname=~'{db_pattern}'}}")
        commits = run_q(f"pg_stat_database_xact_commit{{datname=~'{db_pattern}'}}")
        rollbacks = run_q(f"pg_stat_database_xact_rollback{{datname=~'{db_pattern}'}}")

        # === Instance Summary Metrics (mirrors PMM PostgreSQL Instance Summary dashboard) ===
        conn_active = run_q(f"pg_stat_activity_count{{datname=~'{db_pattern}',state='active'}}")
        conn_idle   = run_q(f"pg_stat_activity_count{{datname=~'{db_pattern}',state='idle'}}")
        conn_wait   = run_q(f"pg_stat_activity_count{{datname=~'{db_pattern}',wait_event_type='Lock'}}")
        qps_data       = run_q(f"rate(pg_stat_database_xact_commit{{datname=~'{db_pattern}'}}[5m])")
        deadlock_rate  = run_q(f"rate(pg_stat_database_deadlocks{{datname=~'{db_pattern}'}}[5m])")
        conflict_rate  = run_q(f"rate(pg_stat_database_conflicts{{datname=~'{db_pattern}'}}[5m])")
        locks_data     = run_q(f"pg_locks_count{{datname=~'{db_pattern}'}}")
        tup_fetched    = run_q(f"rate(pg_stat_database_tup_fetched{{datname=~'{db_pattern}'}}[5m])")
        tup_returned   = run_q(f"rate(pg_stat_database_tup_returned{{datname=~'{db_pattern}'}}[5m])")
        tup_inserted   = run_q(f"rate(pg_stat_database_tup_inserted{{datname=~'{db_pattern}'}}[5m])")
        tup_updated    = run_q(f"rate(pg_stat_database_tup_updated{{datname=~'{db_pattern}'}}[5m])")
        tup_deleted    = run_q(f"rate(pg_stat_database_tup_deleted{{datname=~'{db_pattern}'}}[5m])")
        temp_files     = run_q(f"pg_stat_database_temp_files{{datname=~'{db_pattern}'}}")
        temp_bytes     = run_q(f"pg_stat_database_temp_bytes{{datname=~'{db_pattern}'}}")

        # Build dictionary of metrics grouped by database
        db_metrics = {}
        for db_name in db_filters:
            db_metrics[db_name] = {
                "hit": 0.0, "read": 0.0, "deadlocks": 0.0, "commits": 0.0, "rollbacks": 0.0,
                "conn_active": 0.0, "conn_idle": 0.0, "conn_wait": 0.0,
                "qps": 0.0, "deadlock_rate": 0.0, "conflict_rate": 0.0,
                "locks": {},
                "tup_fetched": 0.0, "tup_returned": 0.0,
                "tup_inserted": 0.0, "tup_updated": 0.0, "tup_deleted": 0.0,
                "temp_files": 0.0, "temp_bytes": 0.0,
            }

        def fill(results, key):
            for r in results:
                db_name = r.get("metric", {}).get("datname")
                if db_name in db_metrics:
                    try:
                        db_metrics[db_name][key] += float(r.get("value", [0, 0])[1])
                    except (ValueError, TypeError):
                        pass

        fill(blks_hit, "hit"); fill(blks_read, "read")
        fill(deadlocks_cum, "deadlocks"); fill(commits, "commits"); fill(rollbacks, "rollbacks")
        fill(conn_active, "conn_active"); fill(conn_idle, "conn_idle"); fill(conn_wait, "conn_wait")
        fill(qps_data, "qps"); fill(deadlock_rate, "deadlock_rate"); fill(conflict_rate, "conflict_rate")
        fill(tup_fetched, "tup_fetched"); fill(tup_returned, "tup_returned")
        fill(tup_inserted, "tup_inserted"); fill(tup_updated, "tup_updated"); fill(tup_deleted, "tup_deleted")
        fill(temp_files, "temp_files"); fill(temp_bytes, "temp_bytes")

        # Lock aggregation by mode
        for r in locks_data:
            m = r.get("metric", {})
            db_name = m.get("datname")
            lock_mode = m.get("mode", "unknown")
            if db_name in db_metrics:
                try:
                    db_metrics[db_name]["locks"][lock_mode] = \
                        db_metrics[db_name]["locks"].get(lock_mode, 0) + float(r.get("value", [0, 0])[1])
                except (ValueError, TypeError):
                    pass

        if db_metrics:
            summary_lines.append("\n=== [4] PostgreSQL Instance Summary Metrics (PMM Exporter) ===")
            idx = 1
            for db_name, m in db_metrics.items():
                total_reads   = m["hit"] + m["read"]
                hit_ratio     = (m["hit"] / total_reads * 100) if total_reads > 0 else 100.0
                total_xact    = m["commits"] + m["rollbacks"]
                rollback_ratio = (m["rollbacks"] / total_xact * 100) if total_xact > 0 else 0.0
                conn_total    = m["conn_active"] + m["conn_idle"]
                temp_mb       = m["temp_bytes"] / (1024 * 1024) if m["temp_bytes"] > 0 else 0.0
                lock_summary  = ", ".join(
                    f"{mode}: {int(cnt)}"
                    for mode, cnt in sorted(m["locks"].items(), key=lambda x: -x[1])
                    if cnt > 0
                )[:300] or "ไม่มี"
                tup_read  = m["tup_fetched"] + m["tup_returned"]
                tup_write = m["tup_inserted"] + m["tup_updated"] + m["tup_deleted"]

                summary_lines.append(
                    f"[{idx}] Database: {db_name}\n"
                    f"   --- Connections ---\n"
                    f"   - Active: {m['conn_active']:.0f} | Idle: {m['conn_idle']:.0f} | Total: {conn_total:.0f}"
                    + (f" ⚠️ Waiting on Lock: {m['conn_wait']:.0f}" if m['conn_wait'] > 0 else "") + "\n"
                    f"   --- Query Throughput ---\n"
                    f"   - QPS (commits/s): {m['qps']:.2f} ops/s\n"
                    f"   - Transactions: Commits={m['commits']:.0f} | Rollbacks={m['rollbacks']:.0f} (Rollback Ratio: {rollback_ratio:.2f}%)\n"
                    f"   --- Conflicts & Locks ---\n"
                    f"   - Deadlock Rate: {m['deadlock_rate']:.5f} ops/s (Cumulative: {m['deadlocks']:.0f})\n"
                    f"   - Conflict Rate: {m['conflict_rate']:.5f} ops/s\n"
                    f"   - Lock Counts by Mode: {lock_summary}\n"
                    f"   --- Data Access Pattern (Tuples/s, rate over 5m) ---\n"
                    f"   - Read : Fetched={m['tup_fetched']:.1f}/s | Returned={m['tup_returned']:.1f}/s (Total: {tup_read:.1f}/s)\n"
                    f"   - Write: Insert={m['tup_inserted']:.1f}/s | Update={m['tup_updated']:.1f}/s | Delete={m['tup_deleted']:.1f}/s (Total: {tup_write:.1f}/s)\n"
                    f"   --- Buffer Cache ---\n"
                    f"   - Cache Hit Ratio: {hit_ratio:.2f}% (Hit={m['hit']:.0f} | Disk Read={m['read']:.0f})\n"
                    f"   --- Temp Files (Cumulative Counter ตั้งแต่ DB Startup — ไม่ใช่ Real-time Error) ---\n"
                    f"   - Temp Files (Cumulative): {m['temp_files']:.0f} files | Temp Space (Cumulative): {temp_mb:.2f} MB (⚠️ เป็นค่าสะสมจากอดีต ห้ามใช้สรุปว่า work_mem ปัจจุบันไม่พอ)"
                )
                idx += 1

    except Exception as e:
        print(f"[!] Failed to fetch PMM database metrics: {str(e)}")

    return "\n".join(summary_lines)


def fetch_pmm_os_and_config_metrics(pmm_ip: str, pmm_port: str, pmm_user: str, pmm_password: str, db_filters: list) -> str:
    """
    Fetch OS-level node metrics + PostgreSQL configuration settings from PMM VictoriaMetrics.
    Covers all root-cause dimensions:
      A) PG Configuration — actual tuned values (shared_buffers, work_mem, etc.)
      B) Long-running transactions — idle/stale TX alert
      C) bgwriter/Checkpoint — I/O health indicators
      D) OS Node metrics — CPU%, RAM, Disk I/O, Load per physical server
      E) Table-level bloat — seq scan vs index scan, dead tuples, autovacuum
    """
    print(f"[*] Fetching OS + Config metrics from PMM ({pmm_ip}:{pmm_port})...")
    if not pmm_ip or not pmm_port:
        return ""

    from requests.auth import HTTPBasicAuth
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url    = f"https://{pmm_ip}:{pmm_port}/prometheus/api/v1/query"
    auth   = HTTPBasicAuth(pmm_user, pmm_password)
    lines  = []

    def q(query):
        try:
            r = requests.get(url, params={"query": query}, auth=auth, verify=PMM_VERIFY_SSL, timeout=10)
            if r.status_code == 200:
                return r.json().get("data", {}).get("result", [])
        except Exception as e:
            print(f"  [PMM OS] query error: {e}")
        return []

    def val(row):
        try:
            return float(row.get("value", [0, 0])[1])
        except (ValueError, TypeError):
            return 0.0

    svc_pattern = "|".join(db_filters) if db_filters else ".*"

    # ──────────────────────────────────────────────────────
    # A. PostgreSQL Configuration Settings (actual values)
    # ──────────────────────────────────────────────────────
    try:
        cfg_queries = {
            "max_connections":          f"pg_settings_max_connections{{service_name=~'{svc_pattern}'}}",
            "shared_buffers_bytes":     f"pg_settings_shared_buffers_bytes{{service_name=~'{svc_pattern}'}}",
            "work_mem_bytes":           f"pg_settings_work_mem_bytes{{service_name=~'{svc_pattern}'}}",
            "effective_cache_size_bytes": f"pg_settings_effective_cache_size_bytes{{service_name=~'{svc_pattern}'}}",
            "maintenance_work_mem_bytes": f"pg_settings_maintenance_work_mem_bytes{{service_name=~'{svc_pattern}'}}",
            "random_page_cost":         f"pg_settings_random_page_cost{{service_name=~'{svc_pattern}'}}",
            "max_wal_size_bytes":        f"pg_settings_max_wal_size_bytes{{service_name=~'{svc_pattern}'}}",
            "wal_buffers_bytes":         f"pg_settings_wal_buffers_bytes{{service_name=~'{svc_pattern}'}}",
            "checkpoint_completion_target": f"pg_settings_checkpoint_completion_target{{service_name=~'{svc_pattern}'}}",
            "max_parallel_workers":     f"pg_settings_max_parallel_workers{{service_name=~'{svc_pattern}'}}",
            "max_worker_processes":     f"pg_settings_max_worker_processes{{service_name=~'{svc_pattern}'}}",
            "log_min_duration_statement_seconds": f"pg_settings_log_min_duration_statement_seconds{{service_name=~'{svc_pattern}'}}",
            "autovacuum_vacuum_scale_factor": f"pg_settings_autovacuum_vacuum_scale_factor{{service_name=~'{svc_pattern}'}}",
            "autovacuum_analyze_scale_factor": f"pg_settings_autovacuum_analyze_scale_factor{{service_name=~'{svc_pattern}'}}",
        }

        # Collect per-service
        svc_cfg = {}
        for key, query in cfg_queries.items():
            for row in q(query):
                svc = row.get("metric", {}).get("service_name", "?")
                if svc not in svc_cfg:
                    svc_cfg[svc] = {}
                svc_cfg[svc][key] = val(row)

        if svc_cfg:
            lines.append("\n=== [5A] PostgreSQL Configuration Settings (Actual Runtime Values) ===")
            for svc, cfg in svc_cfg.items():
                sb_gb  = cfg.get("shared_buffers_bytes", 0) / (1024**3)
                wm_mb  = cfg.get("work_mem_bytes", 0) / (1024**2)
                ecs_gb = cfg.get("effective_cache_size_bytes", 0) / (1024**3)
                mwm_mb = cfg.get("maintenance_work_mem_bytes", 0) / (1024**2)
                mwal_gb= cfg.get("max_wal_size_bytes", 0) / (1024**3)
                wbuf_mb= cfg.get("wal_buffers_bytes", 0) / (1024**2)
                rpc    = cfg.get("random_page_cost", 0)
                cct    = cfg.get("checkpoint_completion_target", 0)
                slow_s = cfg.get("log_min_duration_statement_seconds", -1)

                disk_hint = "SSD/NVMe (rpc<=2)" if rpc <= 2 else "HDD (rpc>2)"
                slow_hint = f"{slow_s*1000:.0f} ms" if slow_s >= 0 else "disabled"

                lines.append(
                    f"Service: {svc}\n"
                    f"  max_connections          = {cfg.get('max_connections',0):.0f}\n"
                    f"  shared_buffers           = {sb_gb:.2f} GB\n"
                    f"  work_mem                 = {wm_mb:.0f} MB\n"
                    f"  effective_cache_size     = {ecs_gb:.2f} GB\n"
                    f"  maintenance_work_mem     = {mwm_mb:.0f} MB\n"
                    f"  max_wal_size             = {mwal_gb:.2f} GB\n"
                    f"  wal_buffers              = {wbuf_mb:.0f} MB\n"
                    f"  random_page_cost         = {rpc} → {disk_hint}\n"
                    f"  checkpoint_completion    = {cct}\n"
                    f"  log_min_duration_stmt    = {slow_hint}\n"
                    f"  max_parallel_workers     = {cfg.get('max_parallel_workers',0):.0f}\n"
                    f"  autovacuum_vacuum_scale  = {cfg.get('autovacuum_vacuum_scale_factor',0)}\n"
                    f"  autovacuum_analyze_scale = {cfg.get('autovacuum_analyze_scale_factor',0)}"
                )
    except Exception as e:
        print(f"  [PMM] Config settings error: {e}")

    # ──────────────────────────────────────────────────────
    # B. Long-running Transactions (Root cause: stale connections, locks)
    # ──────────────────────────────────────────────────────
    try:
        max_tx    = q(f"pg_stat_activity_max_tx_duration{{service_name=~'{svc_pattern}'}}")
        max_state = q(f"pg_stat_activity_max_state_duration{{service_name=~'{svc_pattern}'}}")

        tx_by_svc    = {}
        state_by_svc = {}
        for row in max_tx:
            m = row.get("metric", {})
            svc   = m.get("service_name", "?")
            state = m.get("state", "?")
            v     = val(row)
            if v > 0:
                if svc not in tx_by_svc or tx_by_svc[svc][1] < v:
                    tx_by_svc[svc] = (state, v)
        for row in max_state:
            m = row.get("metric", {})
            svc   = m.get("service_name", "?")
            state = m.get("state", "?")
            v     = val(row)
            if v > 0:
                if svc not in state_by_svc or state_by_svc[svc][1] < v:
                    state_by_svc[svc] = (state, v)

        if tx_by_svc or state_by_svc:
            lines.append("\n=== [5B] Long-Running Transactions & Connection Health ===")
            all_svc = set(list(tx_by_svc.keys()) + list(state_by_svc.keys()))
            for svc in sorted(all_svc):
                tx_info    = tx_by_svc.get(svc)
                state_info = state_by_svc.get(svc)
                tx_str     = f"{tx_info[1]:.1f}s (state={tx_info[0]})" if tx_info else "ไม่มี"
                state_str  = f"{state_info[1]:.1f}s (state={state_info[0]})" if state_info else "ไม่มี"
                alert_tx   = " ⚠️ ALERT: Long TX > 60s" if tx_info and tx_info[1] > 60 else ""
                alert_idle = " ⚠️ ALERT: Idle in TX > 300s" if state_info and state_info[1] > 300 else ""
                lines.append(
                    f"Service: {svc}\n"
                    f"  Max Active TX Duration : {tx_str}{alert_tx}\n"
                    f"  Max State Duration     : {state_str}{alert_idle}"
                )
    except Exception as e:
        print(f"  [PMM] Long TX error: {e}")

    # ──────────────────────────────────────────────────────
    # C. bgwriter / Checkpoint Health (Root cause: I/O pressure, WAL)
    # ──────────────────────────────────────────────────────
    try:
        chk_req    = q(f"rate(pg_stat_bgwriter_checkpoints_req_total{{service_name=~'{svc_pattern}'}}[5m])")
        chk_timed  = q(f"rate(pg_stat_bgwriter_checkpoints_timed_total{{service_name=~'{svc_pattern}'}}[5m])")
        buf_backend= q(f"rate(pg_stat_bgwriter_buffers_backend_total{{service_name=~'{svc_pattern}'}}[5m])")
        buf_alloc  = q(f"rate(pg_stat_bgwriter_buffers_alloc_total{{service_name=~'{svc_pattern}'}}[5m])")
        chk_w_time = q(f"rate(pg_stat_bgwriter_checkpoint_write_time_total{{service_name=~'{svc_pattern}'}}[5m])")
        buf_clean  = q(f"rate(pg_stat_bgwriter_buffers_clean_total{{service_name=~'{svc_pattern}'}}[5m])")
        maxwritten = q(f"rate(pg_stat_bgwriter_maxwritten_clean_total{{service_name=~'{svc_pattern}'}}[5m])")

        bgw = {}
        def set_bgw(rows, key):
            for row in rows:
                svc = row.get("metric", {}).get("service_name", "?")
                if svc not in bgw:
                    bgw[svc] = {}
                bgw[svc][key] = val(row)

        set_bgw(chk_req, "chk_req"); set_bgw(chk_timed, "chk_timed")
        set_bgw(buf_backend, "buf_backend"); set_bgw(buf_alloc, "buf_alloc")
        set_bgw(chk_w_time, "chk_w_time"); set_bgw(buf_clean, "buf_clean")
        set_bgw(maxwritten, "maxwritten")

        if bgw:
            lines.append("\n=== [5C] bgwriter / Checkpoint I/O Health ===")
            for svc, m in bgw.items():
                total_chk = m.get("chk_req", 0) + m.get("chk_timed", 0)
                pct_forced = (m.get("chk_req", 0) / total_chk * 100) if total_chk > 0 else 0
                alert_chk  = " ⚠️ Checkpoint Overload (>50% forced)" if pct_forced > 50 else ""
                alert_back = " ⚠️ Backend writing buffers (bgwriter lag)" if m.get("buf_backend", 0) > 0.1 else ""
                alert_max  = " ⚠️ bgwriter maxwritten (buffer pool pressure)" if m.get("maxwritten", 0) > 0 else ""
                lines.append(
                    f"Service: {svc}\n"
                    f"  Checkpoints/s : req={m.get('chk_req',0):.4f} | timed={m.get('chk_timed',0):.4f} | forced%={pct_forced:.1f}%{alert_chk}\n"
                    f"  Buffers/s     : bgwriter_clean={m.get('buf_clean',0):.2f} | backend_write={m.get('buf_backend',0):.4f}{alert_back} | alloc={m.get('buf_alloc',0):.2f}\n"
                    f"  CheckpointWriteTime/s: {m.get('chk_w_time',0):.2f} ms/s{alert_max}"
                )
    except Exception as e:
        print(f"  [PMM] bgwriter error: {e}")

    # ──────────────────────────────────────────────────────
    # D. OS / Node Metrics (Root cause: VM resource constraints)
    # ──────────────────────────────────────────────────────
    try:
        # Map instance UUID → hostname via node_uname_info
        uname_rows = q("node_uname_info")
        instance_map = {}
        for row in uname_rows:
            m    = row.get("metric", {})
            inst = m.get("instance", "?")
            node = m.get("nodename", m.get("hostname", inst))
            instance_map[inst] = node

        # Gather node metrics
        cpu_idle  = q("rate(node_cpu_seconds_total{mode='idle'}[5m])")
        cpu_total = q("rate(node_cpu_seconds_total[5m])")
        mem_total = q("node_memory_MemTotal_bytes")
        mem_avail = q("node_memory_MemAvailable_bytes")
        mem_swap_used = q("node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes")
        load1     = q("node_load1")
        load5     = q("node_load5")
        load15    = q("node_load15")
        disk_rd   = q("rate(node_disk_read_bytes_total[5m])")
        disk_wr   = q("rate(node_disk_written_bytes_total[5m])")
        disk_iops = q("rate(node_disk_reads_completed_total[5m]) + rate(node_disk_writes_completed_total[5m])")
        fs_avail  = q("node_filesystem_avail_bytes{mountpoint='/'}")
        fs_size   = q("node_filesystem_size_bytes{mountpoint='/'}")
        net_rx    = q("rate(node_network_receive_bytes_total{device!='lo'}[5m])")
        net_tx    = q("rate(node_network_transmit_bytes_total{device!='lo'}[5m])")

        # Aggregate per node
        nodes = {}
        def set_node(rows, key, agg="sum"):
            for row in rows:
                inst = row.get("metric", {}).get("instance", "?")
                node = instance_map.get(inst, inst[:12])
                if any(p in node.lower() for p in ['dev', 'staging', 'test']):
                    continue
                if node not in nodes:
                    nodes[node] = {}
                v = val(row)
                if agg == "sum":
                    nodes[node][key] = nodes[node].get(key, 0.0) + v
                else:
                    nodes[node][key] = max(nodes[node].get(key, 0.0), v)

        set_node(cpu_idle, "_cpu_idle_sum")
        set_node(cpu_total, "_cpu_total_sum")
        set_node(mem_total, "mem_total", "max")
        set_node(mem_avail, "mem_avail", "max")
        set_node(mem_swap_used, "swap_used", "max")
        set_node(load1,  "load1",  "max"); set_node(load5,  "load5",  "max"); set_node(load15, "load15", "max")
        set_node(disk_rd, "disk_rd_bytes"); set_node(disk_wr, "disk_wr_bytes")
        set_node(disk_iops, "disk_iops")
        set_node(fs_avail, "fs_avail", "max"); set_node(fs_size, "fs_size", "max")
        set_node(net_rx, "net_rx"); set_node(net_tx, "net_tx")

        if nodes:
            lines.append("\n=== [5D] OS / VM Node Metrics (Root Cause: Resource Constraints) ===")
            for node, m in sorted(nodes.items()):
                # CPU utilization
                idle_sum  = m.get("_cpu_idle_sum", 0)
                total_sum = m.get("_cpu_total_sum", 0)
                cpu_pct   = (1 - idle_sum / total_sum) * 100 if total_sum > 0 else 0

                # RAM
                mem_t_gb  = m.get("mem_total", 0) / (1024**3)
                mem_a_gb  = m.get("mem_avail", 0) / (1024**3)
                mem_u_gb  = mem_t_gb - mem_a_gb
                mem_pct   = (mem_u_gb / mem_t_gb * 100) if mem_t_gb > 0 else 0
                swap_mb   = m.get("swap_used", 0) / (1024**2)

                # Disk I/O
                rd_mb  = m.get("disk_rd_bytes", 0) / (1024**2)
                wr_mb  = m.get("disk_wr_bytes", 0) / (1024**2)
                iops   = m.get("disk_iops", 0)

                # Filesystem /
                fs_a_gb = m.get("fs_avail", 0) / (1024**3)
                fs_t_gb = m.get("fs_size",  0) / (1024**3)
                fs_pct  = ((fs_t_gb - fs_a_gb) / fs_t_gb * 100) if fs_t_gb > 0 else 0

                # Network
                net_rx_mb = m.get("net_rx", 0) / (1024**2)
                net_tx_mb = m.get("net_tx", 0) / (1024**2)

                # Alerts
                alert_cpu  = " ⚠️ HIGH CPU" if cpu_pct > 80 else ""
                alert_ram  = " ⚠️ RAM PRESSURE" if mem_pct > 85 else ""
                alert_swap = " ⚠️ SWAP IN USE" if swap_mb > 100 else ""
                alert_disk = " ⚠️ DISK FULL" if fs_pct > 85 else ""
                alert_io   = " ⚠️ HIGH DISK I/O" if (rd_mb + wr_mb) > 200 else ""

                lines.append(
                    f"Node: {node}\n"
                    f"  --- CPU ---\n"
                    f"  Utilization: {cpu_pct:.1f}%{alert_cpu} | Load: {m.get('load1',0):.2f} / {m.get('load5',0):.2f} / {m.get('load15',0):.2f} (1m/5m/15m)\n"
                    f"  --- Memory ---\n"
                    f"  Used: {mem_u_gb:.2f} GB / {mem_t_gb:.2f} GB ({mem_pct:.1f}%){alert_ram} | Swap Used: {swap_mb:.0f} MB{alert_swap}\n"
                    f"  --- Disk I/O (rate/5m) ---\n"
                    f"  Read: {rd_mb:.2f} MB/s | Write: {wr_mb:.2f} MB/s | IOPS: {iops:.0f}/s{alert_io}\n"
                    f"  --- Disk Space (/) ---\n"
                    f"  Used: {fs_t_gb-fs_a_gb:.1f} GB / {fs_t_gb:.1f} GB ({fs_pct:.1f}% used){alert_disk}\n"
                    f"  --- Network ---\n"
                    f"  RX: {net_rx_mb:.2f} MB/s | TX: {net_tx_mb:.2f} MB/s"
                )
    except Exception as e:
        print(f"  [PMM] OS node metrics error: {e}")

    # ──────────────────────────────────────────────────────
    # E. Table-Level Health (Root cause: missing index, bloat, autovacuum lag)
    # ──────────────────────────────────────────────────────
    try:
        # Top 10 tables with most dead tuples (bloat)
        dead_rows = q(f"topk(10, pg_stat_user_tables_n_dead_tup{{service_name=~'{svc_pattern}'}})")
        # Top 10 tables with highest seq scan rate (missing index)
        seq_rows  = q(f"topk(10, rate(pg_stat_user_tables_seq_scan{{service_name=~'{svc_pattern}'}}[5m]))")
        # Tables where seq_scan >> idx_scan (ratio based)
        idx_rows  = q(f"pg_stat_user_tables_idx_scan{{service_name=~'{svc_pattern}'}}")
        seq_abs   = q(f"pg_stat_user_tables_seq_scan{{service_name=~'{svc_pattern}'}}")

        bloat_list = []
        for row in dead_rows:
            m  = row.get("metric", {})
            v  = val(row)
            if v > 1000:
                bloat_list.append((m.get("service_name","?"), m.get("schemaname","?"), m.get("relname","?"), v))

        seq_list = []
        for row in seq_rows:
            m = row.get("metric", {})
            v = val(row)
            if v > 0.01:
                seq_list.append((m.get("service_name","?"), m.get("schemaname","?"), m.get("relname","?"), v))

        if bloat_list or seq_list:
            lines.append("\n=== [5E] Table-Level Health (Root Cause: Bloat / Missing Index) ===")

        if bloat_list:
            lines.append("  [Dead Tuples — Table Bloat (top tables, >1000 dead rows)]")
            for svc, schema, tbl, dead in sorted(bloat_list, key=lambda x: -x[3])[:8]:
                alert = " ⚠️ VACUUM NEEDED" if dead > 10000 else ""
                lines.append(f"    {svc}.{schema}.{tbl}: {dead:,.0f} dead tuples{alert}")

        if seq_list:
            lines.append("  [High Seq Scan Rate — Potential Missing Index (rate/5m)]")
            for svc, schema, tbl, rate_val in sorted(seq_list, key=lambda x: -x[3])[:8]:
                lines.append(f"    {svc}.{schema}.{tbl}: {rate_val:.2f} seq_scan/s ← consider adding index")

    except Exception as e:
        print(f"  [PMM] Table health error: {e}")

    return "\n".join(lines)


def fetch_direct_db_diagnostics(connections_json_str: str) -> str:
    """
    Directly connect to target database instances to execute deep runtime diagnostic queries.
    Pulls:
      1) Top active running queries & locks currently executing (pg_stat_activity)
      2) Top 5 slowest queries by total execution time (pg_stat_statements)
      3) Tables with high sequential scans vs index scans (missing index detection)
    """
    if not connections_json_str:
        return ""
    import psycopg2
    try:
        conns = json.loads(connections_json_str)
    except Exception as e:
        print(f"[!] Failed to parse db_connections_json: {e}")
        return ""
    
    if not conns:
        return ""
        
    lines = []
    lines.append("\n=== [6] Direct Database Engine Diagnostics (Direct SQL Pull) ===")
    
    for conn_info in conns:
        label = conn_info.get("label", conn_info.get("host", "Unknown Database"))
        host = conn_info.get("host")
        port = conn_info.get("port", 5432)
        dbname = conn_info.get("dbname")
        user = conn_info.get("user")
        password = conn_info.get("password")
        
        if not host or not dbname or not user or not password:
            continue
            
        lines.append(f"\nDatabase Instance: {label} ({host}:{port}/{dbname})")
        
        conn = None
        try:
            conn = psycopg2.connect(
                host=host, 
                port=int(port) if port else 5432, 
                dbname=dbname, 
                user=user, 
                password=password, 
                connect_timeout=3
            )
            cur = conn.cursor()
            
            # A. Active running queries / locks & Wait Event Breakdown
            try:
                cur.execute("""
                    SELECT pid, state, wait_event_type, wait_event,
                           pg_blocking_pids(pid) AS blocking_pids,
                           ROUND(EXTRACT(epoch FROM (now() - query_start))) as duration_sec,
                           SUBSTRING(query FROM 1 FOR 200) as query_str
                    FROM pg_stat_activity 
                    WHERE state != 'idle' AND pid != pg_backend_pid()
                    ORDER BY duration_sec DESC LIMIT 5
                """)
                active = cur.fetchall()
                lines.append("  [Top Active Queries / Locks currently executing]")
                if active:
                    for pid, state, wait_type, wait_ev, blocking, dur, q_text in active:
                        wait_info = f" (Waiting: {wait_type}/{wait_ev})" if wait_type or wait_ev else ""
                        block_info = f" [BLOCKED BY PID {list(blocking)}]" if blocking else ""
                        lines.append(f"    - PID {pid} [{state}] running for {dur}s{wait_info}{block_info}: {q_text.strip()}")
                else:
                    lines.append("    - No active queries currently running.")

                # Wait Event Summary across database
                cur.execute("""
                    SELECT COALESCE(wait_event_type, 'Executing/CPU') AS wait_type,
                           COALESCE(wait_event, 'Active') AS wait_event,
                           count(*) AS cnt
                    FROM pg_stat_activity
                    WHERE state != 'idle' AND pid != pg_backend_pid()
                    GROUP BY wait_event_type, wait_event
                    ORDER BY count(*) DESC LIMIT 5
                """)
                wait_sum = cur.fetchall()
                if wait_sum:
                    lines.append("  [PostgreSQL Wait Event Distribution]")
                    for w_type, w_event, cnt in wait_sum:
                        lines.append(f"    - {w_type} / {w_event}: {cnt} active backends")
            except Exception as e:
                lines.append(f"  [!] Failed to query pg_stat_activity: {e}")
                conn.rollback()
                
            # B. Top 5 slowest queries by total execution time (pg_stat_statements)
            try:
                cur.execute("""
                    SELECT calls, 
                           ROUND(total_exec_time::numeric, 2) as total_ms,
                           ROUND(mean_exec_time::numeric, 2) as mean_ms,
                           ROUND(rows) as rows_processed,
                           SUBSTRING(query FROM 1 FOR 300) as query_str
                    FROM pg_stat_statements 
                    ORDER BY total_exec_time DESC LIMIT 5
                """)
                slow = cur.fetchall()
                lines.append("  [Top 5 Slowest Queries by Total Runtime (pg_stat_statements)]")
                if slow:
                    for calls, tot, mean, rows, q_text in slow:
                        lines.append(f"    - Called {calls} times | Total: {tot:,}ms | Avg: {mean}ms | Rows: {rows:,}\n      Query: {q_text.strip()}")
                else:
                    lines.append("    - No pg_stat_statements records found (Is extension enabled?).")
            except Exception as e:
                lines.append(f"  [!] pg_stat_statements is not enabled or permission denied: {e}")
                conn.rollback()
                
            # C. Tables with high seq scans vs index scans (CUMULATIVE counters)
            try:
                cur.execute("""
                    SELECT schemaname, relname, seq_scan, idx_scan, 
                           n_dead_tup, n_live_tup,
                           CASE WHEN (seq_scan + COALESCE(idx_scan, 0)) > 0 
                                THEN ROUND(100.0 * seq_scan / (seq_scan + COALESCE(idx_scan, 0)), 1)
                                ELSE 0 END as seq_scan_pct,
                           pg_stat_get_last_analyze_time(c.oid) as last_analyze
                    FROM pg_stat_user_tables t
                    JOIN pg_class c ON c.relname = t.relname AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = t.schemaname)
                    WHERE seq_scan > 100 AND (idx_scan = 0 OR seq_scan > idx_scan)
                    ORDER BY seq_scan DESC LIMIT 5
                """)
                tables = cur.fetchall()
                lines.append("  [Tables with High Seq Scan Ratio (⚠️ ค่า seq_scan/idx_scan เป็น CUMULATIVE COUNTER สะสมตั้งแต่ last stats reset ไม่ใช่ค่าปัจจุบัน)]")
                lines.append("  [⚠️ คำเตือน: seq_scan สูงไม่ได้หมายความว่า 'ขาด Index' เสมอ — ต้องตรวจสอบ Index จริงใน Section D ก่อนสรุป]")
                if tables:
                    for schema, relname, seq, idx, dead, live, seq_pct, last_analyze in tables:
                        analyze_str = f" | Last Analyze: {last_analyze}" if last_analyze else ""
                        lines.append(f"    - Table '{schema}.{relname}': {seq:,} Seq Scans vs {idx:,} Index Scans (Seq Ratio: {seq_pct}%){analyze_str} | Dead: {dead:,} | Live: {live:,}")
                else:
                    lines.append("    - No tables with excessive seq scans detected.")
            except Exception as e:
                lines.append(f"  [!] Failed to query table stats: {e}")
                conn.rollback()

            # D. Actual Existing Indexes — ALL indexes in primary schemas (dc for WMS, public for TMS)
            try:
                cur.execute("""
                    SELECT schemaname, tablename, indexname, indexdef 
                    FROM pg_indexes 
                    WHERE schemaname IN ('dc', 'public')
                    ORDER BY schemaname, tablename, indexname
                """)
                all_indexes = cur.fetchall()
                lines.append("  [Existing Indexes in Database (ข้อมูลจริงทั้งหมดดึงสดจาก DB 100% — ต้องใช้ตรวจสอบก่อนแนะนำสร้าง Index ใหม่ทุกครั้ง)]")
                if all_indexes:
                    current_table = None
                    for schema, tbl, idx_name, idx_def in all_indexes:
                        full_table = f"{schema}.{tbl}"
                        if full_table != current_table:
                            current_table = full_table
                            lines.append(f"    📋 Table: {full_table}")
                        lines.append(f"      ✅ {idx_name}: {idx_def}")
                else:
                    lines.append("    - No user indexes found in primary schemas.")
            except Exception as e:
                lines.append(f"  [!] Failed to query pg_indexes: {e}")
                conn.rollback()
                
            cur.close()
            conn.close()
        except Exception as e:
            lines.append(f"  [❌ Connection Failed] {e}")
            if conn:
                try: conn.close()
                except: pass
                
    return "\n".join(lines)


def analyze_logs_with_ai(
    provider: str,
    host_url: str,
    model_name: str,
    logs_text: str, 
    slow_queries_text: str, 
    prometheus_metrics_text: str,
    postgresql_conf: str = None,
    pgbouncer_ini: str = None,
    pg_hba_conf: str = None,
    server_spec: dict = None
) -> str:
    # Truncate text inputs to prevent token context length overflow in LM Studio
    if len(logs_text) > 24000:
        logs_text = logs_text[:24000] + "\n... [TRUNCATED TO PREVENT CONTEXT OVERFLOW] ..."
    if len(slow_queries_text) > 16000:
        slow_queries_text = slow_queries_text[:16000] + "\n... [TRUNCATED TO PREVENT CONTEXT OVERFLOW] ..."
    if len(prometheus_metrics_text) > 16000:
        prometheus_metrics_text = prometheus_metrics_text[:16000] + "\n... [TRUNCATED TO PREVENT CONTEXT OVERFLOW] ..."

    db_config_text = ""
    if postgresql_conf:
        db_config_text += f"\n--- postgresql.conf (Sample) ---\n{postgresql_conf[:8000]}\n"
    if pgbouncer_ini:
        db_config_text += f"\n--- pgbouncer.ini (Sample) ---\n{pgbouncer_ini[:8000]}\n"
    if pg_hba_conf:
        db_config_text += f"\n--- pg_hba.conf (Sample) ---\n{pg_hba_conf[:8000]}\n"

    # Build server hardware spec context block (supports multiple VMs)
    hw_context = ""
    server_specs_list = server_spec if isinstance(server_spec, list) else ([server_spec] if server_spec else [])
    valid_specs = [s for s in server_specs_list if s and any(s.values())]
    if valid_specs:
        hw_lines = [f"\n[Server Infrastructure ({len(valid_specs)} VMs/Servers registered)]"]
        for idx, spec in enumerate(valid_specs, 1):
            hw_lines.append(f"  VM #{idx}: {spec.get('name', 'Unnamed')} — Role: {spec.get('role', 'N/A')}")
            if spec.get('os'):
                hw_lines.append(f"    OS: {spec['os']}")
            if spec.get('cpu_model'):
                hw_lines.append(f"    CPU: {spec['cpu_model']}")
            if spec.get('cpu_cores'):
                hw_lines.append(f"    CPU Cores (Logical): {spec['cpu_cores']} cores")
            if spec.get('ram_gb'):
                hw_lines.append(f"    RAM: {spec['ram_gb']} GB")
            if spec.get('storage_type'):
                sz = f" ({spec['storage_size_gb']} GB)" if spec.get('storage_size_gb') else ""
                hw_lines.append(f"    Storage: {spec['storage_type']}{sz}")
            if spec.get('notes'):
                hw_lines.append(f"    Notes: {spec['notes']}")
        hw_context = "\n".join(hw_lines)

    # Setup Payloads based on native vs OpenAI compatible
    api_url = f"{host_url.rstrip('/')}/chat/completions"
    
    is_ollama_native = False
    if provider == "ollama" and "/v1" not in host_url and ":11434" in host_url:
        api_url = f"{host_url.rstrip('/')}/api/chat"
        is_ollama_native = True

    # Prompt Template
    system_prompt = (
        "คุณคือผู้เชี่ยวชาญด้าน DevOps, System Administrator และ Senior Database Administrator (DBA) "
        "หน้าที่ของคุณคือวิเคราะห์คอขวดระบบ ปัญหาประสิทธิภาพ และวิเคราะห์ให้คำแนะนำจูนค่าฐานข้อมูล PostgreSQL/PgBouncer เพื่อแก้ไขปัญหา\n\n"
        "กฎเหล็กสำคัญในการวิเคราะห์และตอบคำถาม:\n"
        "1. [เรื่อง Schema ห้ามเดาเด็ดขาด]:\n"
        "   - ในฐานข้อมูล wms: ตารางส่วนใหญ่อยู่ใน schema 'dc' (เช่น dc.wms_location, dc.wms_users, dc.wms_employees) ห้ามอ้างอิงเป็น public\n"
        "   - ในฐานข้อมูล tms: ตารางส่วนใหญ่อยู่ใน schema 'public' (เช่น public.tms_master_mapping_code)\n"
        "2. [ตรวจสอบ Index ที่มีอยู่แล้ว - Query-First Policy]:\n"
        "   - ใน Section [6] Section D '[Existing Indexes in Database]' ระบบได้ทำการ QUERY รายชื่อ Index ทั้งหมด 100% จาก DB จริง (ทั้ง schema 'dc' ของ WMS และ schema 'public' ของ TMS) มาให้แล้ว\n"
        "   - ก่อนเสนอคำแนะนำสร้าง Index ใหม่บนตารางใดๆ คุณต้องตรวจสอบ Section D ของตารางนั้นๆ ทีละตัวก่อนเสมอ:\n"
        "     * Primary Key (pkey) คือ Index (B-Tree Unique Index) อยู่แล้ว เช่น `wms_location_pkey` บน `location_id` **ห้ามเสนอสร้าง Index บนคอลัมน์ที่เป็น Primary Key ซ้ำเด็ดขาด!**\n"
        "     * คอลัมน์แรกใน Composite Index หรือ Unique Key (เช่น `product_code` ใน `idx_location_onhand_pick (product_code, company_id, ...)`) ถือว่ามี Index ครอบคลุมแล้ว **ห้ามเสนอสร้าง Index เดี่ยวซ้ำอีก!**\n"
        "     * หากพบว่าใน Section D มี Index ที่ครอบคลุมคอลัมน์นั้นแล้ว -> **ห้ามใส่คำสั่ง CREATE INDEX ใน Action Plan เด็ดขาด!** ให้ระบุในสรุปผลว่า 'ตรวจสอบแล้ว มี Index ครอบคลุมแล้ว ดำเนินการเสร็จสิ้น'\n"
        "     * อนุญาตให้สร้างคำสั่ง `CREATE INDEX CONCURRENTLY IF NOT EXISTS` ใน Action Plan ได้เฉพาะคอลัมน์ที่ตรวจสอบใน Section D แล้วพบว่า **ยังไม่มี Index อยู่เลยจริงๆ** เท่านั้น\n"
        "3. [คอลัมน์และคีย์เวิร์ดที่ถูกต้อง]:\n"
        "   - สำหรับตาราง dc.wms_users คอลัมน์เก็บชื่อผู้ใช้คือ 'user_name' (ไม่ใช่ username)\n"
        "   - สำหรับตาราง public.tms_master_mapping_code คอลัมน์หลักคือ 'code_type' และ 'code_value' (ไม่ใช่ mapping_code)\n"
        "4. [การสร้างดัชนีออนไลน์]:\n"
        "   - ทุกคำแนะนำการสร้าง Index บนตารางใช้งานจริง ต้องใช้คำสั่งแบบไม่ล็อกตาราง 'CREATE INDEX CONCURRENTLY IF NOT EXISTS' เสมอ\n"
        "5. [Production Stability Protocol - ห้ามปรับ Global Config สลับไปมา]:\n"
        "   - ห้ามแนะนำให้ปรับเปลี่ยนค่า Config ใน postgresql.conf (เช่น work_mem, shared_buffers) หรือ pgbouncer.ini (เช่น default_pool_size) ขึ้นๆ ลงๆ สลับไปมาเด็ดขาด!\n"
        "   - ยึดถือค่าปัจจุบันในระบบเป็น Baseline ที่เสถียรเสมอ\n"
        "   - ค่า 'Temp Files' ใน PMM เป็นค่าสะสม (Cumulative) ตั้งแต่เปิดเครื่อง DB ห้ามนำมาอ้างว่าเป็นปัญหา Memory ไม่พอเพื่อขอเพิ่ม work_mem เว้นแต่จะมี Real-time Error ใน Log หรือ OOM\n"
        "   - หาก 'Clients Waiting' ใน PgBouncer เท่ากับ 0 ห้ามแนะนำปรับเพิ่ม default_pool_size เด็ดขาด\n"
        "6. [Direct Database Access - คุณเข้าถึงฐานข้อมูลได้โดยตรง]:\n"
        "   - ห้ามตอบว่า 'ผมไม่สามารถเชื่อมต่อ Database ได้โดยตรง' เด็ดขาด เพราะระบบนี้มี Diagnostic SQL Engine ที่เชื่อมต่อตรงเข้าสู่ PostgreSQL ของ WMS-DB (10.1.1.9) และ TMS-DB (10.1.1.24) อยู่แล้ว\n"
        "   - ข้อมูลใน Section '=== [6] Direct Database Engine Diagnostics (Direct SQL Pull) ===' คือผลลัพธ์สดที่ดึงตรงจากฐานข้อมูลจริง ให้อ้างอิงข้อมูลในนี้เพื่อตอบคำถามเรื่อง Index, Active Queries, Slow Queries และ Table Stats ได้ทันที\n"
        "   - หากผู้ใช้ถามว่า 'ตรวจสอบ Index ให้หน่อย' หรือ 'Query ดูให้หน่อย' ให้ตอบจากข้อมูลที่มีอยู่ใน Section [6] โดยตรง ไม่ต้องบอกให้ผู้ใช้ไปรัน SQL เอง\n"
        "7. [Query-First Policy - ตรวจสอบข้อมูลจริงก่อนแนะนำเสมอ]:\n"
        "   - ก่อนจะแนะนำหรือเสนอ Suggestion ใดๆ (เช่น สร้าง Index, ปรับ Config, หรือแก้ไข Query) ต้องตรวจสอบข้อมูลจริงจาก Section [6] Direct Database Engine Diagnostics ก่อนเสมอ\n"
        "   - หากข้อมูลใน Section [6] ระบุว่ามี Index นั้นอยู่แล้ว (รวมถึง partial index หรือ unique index บนคอลัมน์เดียวกัน) หรือค่า Config ปัจจุบันเหมาะสมแล้ว ห้ามแนะนำซ้ำ ให้ระบุสถานะเป็น 'ตรวจสอบแล้ว ดำเนินการเสร็จสิ้น'\n"
        "   - ทุกคำแนะนำต้องอ้างอิงหลักฐานจากข้อมูลจริงในรายงานเท่านั้น ห้ามเดาหรือสมมติสถานะของระบบ\n"
        "8. [Cumulative Counter Awareness - เข้าใจค่าสะสม]:\n"
        "   - ค่า seq_scan และ idx_scan ใน pg_stat_user_tables เป็นค่า CUMULATIVE (สะสมตั้งแต่ last stats reset) ไม่ใช่ค่าปัจจุบัน\n"
        "   - seq_scan สูง ไม่ได้หมายความว่า 'ขาด Index' เสมอ! อาจเป็นค่าสะสมจากก่อนที่จะสร้าง Index\n"
        "   - ก่อนสรุปว่าตารางใด 'ขาด Index' ต้องตรวจสอบรายการ Index จริงใน Section D '[Existing Indexes in Database]' ก่อนเสมอ\n"
        "   - หาก Section D แสดงว่าตารางมี Index ครอบคลุมคอลัมน์ที่ใช้ Filter/Sort แล้ว ให้สรุปว่า 'มี Index ครอบคลุมแล้ว ค่า seq_scan ที่สูงเป็นค่าสะสมจากอดีต' และห้ามแนะนำสร้าง Index ซ้ำ\n"
        "9. [Production-Only Focus - ห้ามกล่าวถึง Dev/Staging เด็ดขาด]:\n"
        "   - ให้โฟกัสวิเคราะห์และแนะนำเฉพาะ Production Nodes เท่านั้น ได้แก่ WMS-DB-Prod (10.1.1.9) และ TMS-DB-Prod (10.1.1.24)\n"
        "   - ห้ามกล่าวถึง ห้ามเอ่ยชื่อ ห้ามวิเคราะห์ และห้ามใส่ Node ที่เป็น Dev/Staging (เช่น dev-db-tms, dev-db-wms) ลงในรายงานหรือ Action Plan โดยเด็ดขาด!\n"
        "10. [รูปแบบการตอบ - ห้ามใช้ HTML ใน Markdown เด็ดขาด]:\n"
        "   - ห้ามใช้แท็ก HTML ทุกชนิดในการตอบ เช่น <br>, <br/>, <br />, <b>, <i>, <ul>, <li> โดยเด็ดขาด!\n"
        "   - เมื่อต้องการขึ้นบรรทัดใหม่ใน Table Cell ให้ใช้วิธีทำ Cell สั้นๆ กระชับ หรือแบ่งออกเป็นหลาย Row แทน ห้ามใส่ <br> ใน Cell เด็ดขาด!\n"
        "   - เมื่อต้องการแสดงตัวอย่าง SQL หรือ Command ใน Action Plan ให้ใช้ Code Block (```sql หรือ ```bash) แยกออกมานอก Table แทน\n"
        "   - ผลลัพธ์ทั้งหมดต้องเป็น Clean Markdown เท่านั้น ไม่มี HTML ปนเลย"
        + (f"\n\n{hw_context}" if hw_context else "")
    )
    user_prompt = f"""จงวิเคราะห์ Log ของระบบ WMS/TMS, ข้อมูล SQL Slow Queries จาก Percona Monitoring & Management (PMM), ข้อมูลทรัพยากรคอนเทนเนอร์จาก Prometheus (cAdvisor) และ **เปรียบเทียบกับค่าตั้งค่าฐานข้อมูลปัจจุบัน (DB Configuration Files)** ต่อไปนี้ เพื่อระบุแยกแยะจุดคอขวดระหว่าง Network/Frontend, Backend (Spring Boot), Database (PostgreSQL) และระดับทรัพยากรเครื่อง (CPU/Memory) รวมถึงตรวจสอบหา Error ที่ซ่อนอยู่ และให้แนวทางการจูนค่าปรับปรุง Database/PgBouncer Config ที่มีประสิทธิภาพสอดคล้องกับพฤติกรรมของระบบจริง

เกณฑ์การพิจารณาประสิทธิภาพ:
1. หากค่า TotalTime สูง แต่ค่า SpringBootTime ต่ำอย่างเห็นได้ชัด -> สาเหตุเกิดจาก Network Overhead / Frontend
2. หากค่า TotalTime สูง และค่า SpringBootTime สูงในระดับที่ใกล้เคียงกัน -> สาเหตุเกิดจากฝั่ง Backend/API (Spring Boot ทำงานช้า)
3. หากฝั่ง Backend ช้า ให้ตรวจสอบข้อมูล SQL Slow Queries จาก PMM ด้านล่างว่ามีความช้าที่สัมพันธ์กันหรือไม่ (เช่น มี SQL Query ตัวใดที่รันเฉลี่ยช้าและใช้บ่อยในฐานข้อมูล wms/tms)
4. ร่วมกับการตรวจสอบ Resource Metrics จาก Prometheus เพื่อดูว่ามีตู้คอนเทนเนอร์ตัวใด (เช่น dc-backend-prod, tms-backend-prod) ที่มีอาการ CPU พุ่งทะลุ (High CPU) หรือ Memory สูงผิดปกติจนทำให้แอปพลิเคชันตอบสนองช้าลงหรือไม่
5. ตรวจสอบว่าในบรรทัดที่เกิดความช้า มีข้อความแจ้งเตือน Error บันทึกอยู่, พ่น HTTP Status 5xx หรือมี Exception โผล่มาด้วยหรือไม่
6. **เปรียบเทียบและวิเคราะห์ค่าคอนฟิกฐานข้อมูล**: ตรวจดูความจุการเชื่อมต่อ (Connections), ขนาดแรมจัดสรร (Shared Buffers, Work Mem), และความปลอดภัยใน pg_hba.conf โดยตรวจสอบว่าตั้งค่าขัดแย้งหรือสอดคล้องกับอาการของโหลดงานจริงหรือไม่ และแนะนำการปรับจูนที่เป็นรูปธรรมในส่วนท้ายสุดของการวิเคราะห์

จงสรุปผลวิเคราะห์เป็นภาษาไทยให้กระชับ ตรงประเด็น เป็นข้อๆ (ไม่เกิน 4 ข้อ) โดยระบุชื่อ Endpoint Path, คำสั่ง SQL/ตารางคอขวด, ชื่อคอนเทนเนอร์ที่มีปัญหาทรัพยากรให้ชัดเจน และเพิ่มข้อแนะนำการจูนค่าคอนฟิกฐานข้อมูลและแผนดำเนินการปฏิบัติจริงทีละขั้นตอน (Step-by-step Action Plan) เช่นการระบุพาธไฟล์คอนฟิก (เช่น /etc/postgresql/16/main/postgresql.conf หรือ /etc/pgbouncer/pgbouncer.ini) คีย์เวิร์ดที่ต้องแก้ไข และคำสั่งสั่ง Reload/Restart (เช่น SELECT pg_reload_conf(); หรือ docker compose restart) ต่อท้ายเป็นข้อที่ 5 (ถ้ามีคำแนะนำที่เป็นประโยชน์สอดคล้องกับปัญหานั้นๆ)

**กฎการจัดรูปแบบ (ห้ามละเมิด):**
- ห้ามใช้ HTML แท็กทุกชนิดในผลลัพธ์ โดยเฉพาะ `<br>`, `<br/>`, `<b>`, `<i>` เด็ดขาด!
- หาก Table Cell มีข้อมูลหลายบรรทัด ให้แบ่งเป็นหลาย Row หรือทำให้กระชับในบรรทัดเดียว
- หากต้องการแสดงตัวอย่าง SQL/Command ให้ใช้ Code Block แยกออกมานอก Table
- Output ต้องเป็น Pure Markdown เท่านั้น ไม่มี HTML ใดๆ

Logs ที่ระบุพบจากระบบ (Nginx/NPM):
{logs_text}

SQL Slow Queries จาก PMM QAN:
{slow_queries_text}

cAdvisor Container Metrics (Prometheus):
{prometheus_metrics_text}

{f"Database Configuration Files เพื่อนำมาร่วมวิเคราะห์จูนค่า: {db_config_text}" if db_config_text else ""}"""

    # Setup Payloads based on native vs OpenAI compatible
    if is_ollama_native:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "options": {"temperature": 0.2},
            "stream": False
        }
    else:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "stream": False
        }

    try:
        response = requests.post(api_url, json=payload, timeout=600)
        if response.status_code == 200:
            resp_data = response.json()
            if is_ollama_native:
                return resp_data.get("message", {}).get("content", "No content returned from Ollama")
            else:
                return resp_data['choices'][0]['message']['content']
        else:
            return f"AI Provider API Error: Status {response.status_code} - {response.text}"
    except Exception as e:
        return f"ไม่สามารถเชื่อมต่อไปยัง AI Provider ({provider} @ {host_url}) ได้: {str(e)}"

def generate_daily_ai_summary(
    provider: str,
    host_url: str,
    model_name: str,
    date_str: str,
    reports: list
) -> str:
    print(f"[*] Generating daily summary for date: {date_str} across {len(reports)} reports...")
    if not reports:
        return "ไม่มีรายงานสำหรับการสรุปรายวันในวันที่ระบุ"

    # Aggregating summaries of all runs (use enumerate for daily run index, not DB ID)
    # Truncate each run summary to prevent context overflow when many runs exist
    MAX_SUMMARY_CHARS_PER_RUN = 3000
    aggregated_text = ""
    for run_idx, r in enumerate(reports, start=1):
        # Format time of report
        run_time = r.timestamp.strftime("%H:%M:%S")
        aggregated_text += f"\n--- Run #{run_idx} at {run_time} (Status: {r.status.upper()}) ---\n"
        if r.status == "success":
            summary_content = r.summary or "ไม่มีสรุปวิเคราะห์"
            if len(summary_content) > MAX_SUMMARY_CHARS_PER_RUN:
                summary_content = summary_content[:MAX_SUMMARY_CHARS_PER_RUN] + "\n... [TRUNCATED] ..."
            aggregated_text += f"{summary_content}\n"
        else:
            aggregated_text += f"การวิเคราะห์ล้มเหลว: {r.error_message or 'ไม่ระบุสาเหตุ'}\n"

    # Setup Prompt
    system_prompt = (
        "คุณคือผู้เชี่ยวชาญด้าน DevOps, System Administrator และ Senior Database Administrator (DBA) "
        "หน้าที่ของคุณคือการอ่านบทวิเคราะห์ของระบบในแต่ละช่วงเวลา และเขียนสรุปภาพรวมรายวัน จับแนวโน้ม คอขวดที่เกิดซ้ำๆ พร้อมให้คำแนะนำวิธีแก้ไขปัญหาระดับโครงสร้างระบบและฐานข้อมูล\n\n"
        "กฎเหล็กสำคัญในการวิเคราะห์และสรุปผล:\n"
        "1. [เรื่อง Schema และตาราง]: ห้ามสมมติว่าตารางทั้งหมดอยู่ใน schema 'public' เสมอไป ให้เคารพ schema 'dc' ของตารางฝั่ง wms และ 'public' ของฝั่ง tms\n"
        "2. [ดัชนีที่ได้รับการสร้างแล้ว]: หากในรายงานย่อยมีการระบุว่าสร้างดัชนีบางตัวเรียบร้อยแล้วและสถานะเสร็จสิ้น (เช่น idx_wms_loc_code หรือ idx_wms_users_username) ในหัวข้อที่ 5 (Action Plan) ของสรุปภาพรวมประจำวัน จะต้องสรุปคิวรีเหล่านี้เป็นงานที่ทำเสร็จแล้ว (Completed) และห้ามจัดไว้เป็นงานที่ต้องทำต่อ (Pending)\n"
        "3. [Production Stability Protocol - ห้ามปรับ Global Config สลับไปมา]: ห้ามเสนอให้ปรับเปลี่ยนค่า Config ใน postgresql.conf (เช่น work_mem, shared_buffers) ขึ้นๆ ลงๆ สลับไปมาในรายงานประจำวันเด็ดขาด หากไม่มีหลักฐานความผิดปกติเกี่ยวกับ Memory ใน Log ชัดเจน (เช่น เกิด temporary file หรือ OOM) ให้ยึดถือค่าปัจจุบันเป็น Baseline ที่เสถียรไว้เสมอ"
    )
    
    user_prompt = f"""นี่คือข้อมูลดิบจากการสรุปรายงานย่อยของการรันวิเคราะห์ระบบ WMS/TMS รายวินาที ประจำวันที่ {date_str} ทั้งหมด {len(reports)} รายการ:

{aggregated_text}

จงวิเคราะห์และสรุป "รายงานวิเคราะห์และสรุปแนวทางแก้ไขภาพรวมประจำวัน" เป็นภาษาไทย โดยตอบเป็นหัวข้อดังต่อไปนี้อย่างกระชับและตรงประเด็น:

1. **สรุปภาพรวมสถานะระบบรายวัน (Daily System Overview)**: ภาพรวมการรันวิเคราะห์ในวันนี้ สำเร็จ/ล้มเหลวทั้งหมดกี่ครั้ง และประเมินความสถียร/ความเชื่อมั่นของบริการ
2. **แนวโน้มและรูปแบบคอขวดที่เกิดซ้ำ (Daily Bottleneck & Trend Patterns)**: ปัญหาใดเป็นปัญหาหลักที่ตรวจพบซ้ำๆ ในวันนี้ (เช่น CPU Peak ช่วงเวลาใดเวลาหนึ่ง, ปัญหา PgBouncer ล็อกเชื่อมต่อค้าง, หรือมี Slow SQL Query ตัวไหนพบบ่อยที่สุด)
3. **สาเหตุของปัญหาระดับสถาปัตยกรรม (Architectural Root Cause Hypothesis)**: การประเมินทาง DevOps/DBA ว่าทำไมปัญหานี้ถึงเกิดขึ้นเป็นระบบในวันนี้ (เช่น ขนาดของ pool ไม่เหมาะสม, ปัญหาจากแอปพลิเคชันไม่ปิดการเชื่อมต่อ, หรือการขาด Index ในบางตาราง)
4. **แนวทางแก้ไขและจูนระบบระยะยาว (Long-term Tuning & Architectural Recommendations)**: คำแนะนำที่เป็นขั้นตอนชัดเจนในการแก้ไขปัญหานี้เชิงรุก (Proactive) เช่น การจูน config ของ PostgreSQL/PgBouncer, การตั้งค่าการจำกัด CPU/Memory คอนเทนเนอร์ หรือแนวทางแก้ฝั่งซอร์สโค้ด
5. **แผนดำเนินการปฏิบัติจริงทีละขั้นตอน (Action Plan & Step-by-step Guide)**: สำหรับทุกคำแนะนำการจูนและแก้ไขข้างต้น ให้เขียนแจกแจงขั้นตอนวิธีปฏิบัติจริงอย่างละเอียดและเข้าใจง่าย (เช่น ระบุพาธไฟล์ที่ต้องแก้ไข เช่น `/etc/postgresql/16/main/postgresql.conf` หรือ `/etc/pgbouncer/pgbouncer.ini` บรรทัดหรือคีย์เวิร์ดที่ต้องแก้ไข และคำสั่งสั่งการสั่ง Reload/Restart เช่น `SELECT pg_reload_conf();` หรือคำสั่งรันสร้าง Index เพื่อให้ทีมแอดมินนำไปทำงานต่อได้ทันที)

โปรดจัดทำเนื้อหาในรูปแบบ Markdown ที่สวยงาม อ่านง่าย และเป็นระเบียบ"""

    # Setup Payloads based on native vs OpenAI compatible
    api_url = f"{host_url.rstrip('/')}/chat/completions"
    
    is_ollama_native = False
    if provider == "ollama" and "/v1" not in host_url and ":11434" in host_url:
        api_url = f"{host_url.rstrip('/')}/api/chat"
        is_ollama_native = True

    if is_ollama_native:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "options": {"temperature": 0.2},
            "stream": False
        }
    else:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "stream": False
        }

    try:
        response = requests.post(api_url, json=payload, timeout=600)
        if response.status_code == 200:
            resp_data = response.json()
            if is_ollama_native:
                return resp_data.get("message", {}).get("content", "No content returned from Ollama")
            else:
                choices = resp_data.get('choices', [])
                if not choices:
                    return "AI model returned empty response (no choices). Model may have rejected the request."
                return choices[0].get('message', {}).get('content', 'No content in AI response')
        else:
            return f"AI Provider API Error: Status {response.status_code} - {response.text}"
    except Exception as e:
        return f"ไม่สามารถเชื่อมต่อไปยัง AI Provider ({provider} @ {host_url}) ได้: {str(e)}"

def run_analysis_job(db: Session, report_id: int):
    # Fetch report placeholder
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return
        
    # Fetch active settings (always ID=1)
    setting = db.query(Setting).filter(Setting.id == 1).first()
    if not setting:
        report.status = "failed"
        report.error_message = "No application settings configured."
        db.commit()
        return

    try:
        # 1. Parse lists
        loki_projects = json.loads(setting.loki_projects)
        pmm_db_filters = json.loads(setting.pmm_db_filters)
        lookback_mins = setting.lookback_minutes or 15
        
        # 2. Fetch data
        logs_text = fetch_loki_logs(setting.loki_ip, loki_projects, lookback_mins)
        slow_queries_text = fetch_pmm_slow_queries(
            setting.pmm_ip, 
            setting.pmm_port, 
            setting.pmm_user, 
            setting.pmm_password, 
            pmm_db_filters,
            lookback_mins
        )
        prometheus_metrics_text = fetch_prometheus_metrics(
            setting.prometheus_ip,
            setting.prometheus_port,
            loki_projects,
            lookback_mins
        )
        
        # 2b. Fetch PMM Deep Database Metrics
        pmm_db_metrics_text = fetch_pmm_database_metrics(
            setting.pmm_ip,
            setting.pmm_port,
            setting.pmm_user,
            setting.pmm_password,
            pmm_db_filters
        )
        if pmm_db_metrics_text:
            prometheus_metrics_text += "\n" + pmm_db_metrics_text

        # 2c. Fetch PMM OS + Config + Table-level metrics (Root Cause Analysis)
        pmm_os_config_text = fetch_pmm_os_and_config_metrics(
            setting.pmm_ip,
            setting.pmm_port,
            setting.pmm_user,
            setting.pmm_password,
            pmm_db_filters
        )
        if pmm_os_config_text:
            prometheus_metrics_text += "\n" + pmm_os_config_text
        
        # 2d. Fetch Direct DB Diagnostics (Active queries, lock blockages, missing index stats)
        direct_db_text = fetch_direct_db_diagnostics(setting.db_connections_json)
        if direct_db_text:
            prometheus_metrics_text += "\n" + direct_db_text

        
        # Save raw data to report
        report.nginx_logs = logs_text
        report.slow_queries = slow_queries_text
        report.prometheus_metrics = prometheus_metrics_text
        db.commit()
        
        summary = analyze_logs_with_ai(
            setting.ai_provider,
            setting.ai_host_url,
            setting.ai_model_name,
            logs_text,
            slow_queries_text,
            prometheus_metrics_text,
            setting.postgresql_conf,
            setting.pgbouncer_ini,
            setting.pg_hba_conf,
            server_spec=json.loads(setting.server_specs_json) if setting.server_specs_json else None
        )
        
        # 4. Save and Archive
        if summary.startswith("ไม่สามารถเชื่อมต่อ") or summary.startswith("AI Provider API Error"):
            report.status = "failed"
            report.error_message = summary
            report.summary = None
        else:
            report.summary = summary
            report.status = "success"
        db.commit()
        
        # Upload archive to Minio
        object_name = upload_report_archive(report.id, logs_text, slow_queries_text, prometheus_metrics_text, summary)
        if object_name:
            report.minio_object_name = object_name
            db.commit()
            print(f"[+] Report {report.id} archived in Minio as {object_name}")
            
    except Exception as e:
        report.status = "failed"
        report.error_message = str(e)
        db.commit()
        print(f"[!] Analysis job failed: {str(e)}")

def call_chat_ai(
    provider: str,
    host_url: str,
    model_name: str,
    messages_history: list,
    system_prompt: str
) -> str:
    api_url = f"{host_url.rstrip('/')}/chat/completions"
    
    is_ollama_native = False
    if provider == "ollama" and "/v1" not in host_url and ":11434" in host_url:
        api_url = f"{host_url.rstrip('/')}/api/chat"
        is_ollama_native = True

    # Combine system prompt with conversation history
    messages = [{"role": "system", "content": system_prompt}] + messages_history

    if is_ollama_native:
        payload = {
            "model": model_name,
            "messages": messages,
            "options": {"temperature": 0.5},
            "stream": False
        }
    else:
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.5,
            "stream": False
        }

    try:
        response = requests.post(api_url, json=payload, timeout=120)
        if response.status_code == 200:
            resp_data = response.json()
            if is_ollama_native:
                return resp_data.get("message", {}).get("content", "No response content from Ollama")
            else:
                choices = resp_data.get('choices', [])
                if not choices:
                    return "AI model returned empty response (no choices). Model may have rejected the request."
                return choices[0].get('message', {}).get('content', 'No content in AI response')
        else:
            return f"AI Provider API Error: Status {response.status_code} - {response.text}"
    except Exception as e:
        return f"ไม่สามารถเชื่อมต่อไปยัง AI Provider ({provider} @ {host_url}) ได้: {str(e)}"

