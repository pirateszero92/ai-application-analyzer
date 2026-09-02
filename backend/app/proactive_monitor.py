"""
proactive_monitor.py - Proactive AI Health Monitor for WMS/TMS Systems.
"""

import json
import time
import re
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_SAFE_PROJECT_NAME = re.compile(r'^[a-zA-Z0-9_-]+$')
ALERT_DEBOUNCE_TTL = 900

THRESHOLDS = {
    "cpu_warn": 70.0,
    "cpu_crit": 85.0,
    "pgb_wait_warn": 3,
    "pgb_wait_crit": 10,
    "long_query_warn_s": 30,
    "long_query_crit_s": 60,
    "db_conn_warn_pct": 70.0,
    "db_conn_crit_pct": 90.0,
    "error_rate_warn": 5,
    "error_rate_crit": 20,
    "hikari_pending_warn": 1,
    "hikari_pending_crit": 5,
    "jvm_heap_warn": 80.0,
    "jvm_heap_crit": 92.0,
    "jvm_gc_pause_warn_s": 1.0,
    "jvm_gc_pause_crit_s": 3.0,
}


def _get_redis(redis_url: str):
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(redis_url, socket_timeout=3)
        r.ping()
        return r
    except Exception as e:
        print(f"[Proactive] Redis unavailable: {e}")
        return None


def _is_debounced(r, alert_key: str) -> bool:
    if r is None:
        return False
    return bool(r.exists(f"ai_analyzer:proactive_alert:{alert_key}"))


def _set_debounce(r, alert_key: str):
    if r:
        r.set(f"ai_analyzer:proactive_alert:{alert_key}", "1", ex=ALERT_DEBOUNCE_TTL)


# ─────────────────────────────────────────────────
# Metric Fetchers
# ─────────────────────────────────────────────────

def _fetch_container_metrics(prometheus_ip: str, prometheus_port: str, projects: list) -> dict:
    """Returns {container_name: {cpu_pct, mem_mb}} from Prometheus instant query."""
    results = {}
    if not prometheus_ip or not projects:
        return results

    base = f"http://{prometheus_ip}:{prometheus_port}/api/v1/query"
    safe_projects = [p for p in projects if _SAFE_PROJECT_NAME.match(str(p))]
    if not safe_projects:
        return results

    container_jobs = "|".join([f"{p}-prod-containers" for p in safe_projects])
    cpu_q = (f'sum(rate(container_cpu_usage_seconds_total{{job=~"{container_jobs}",'
             f'container!="POD",container!=""}}[5m])) by (container) * 100')
    mem_q = (f'container_memory_working_set_bytes{{job=~"{container_jobs}",'
             f'container!="POD",container!=""}}')

    try:
        r_cpu = requests.get(base, params={"query": cpu_q}, timeout=8)
        r_mem = requests.get(base, params={"query": mem_q}, timeout=8)

        if r_cpu.status_code == 200:
            for item in r_cpu.json().get("data", {}).get("result", []):
                name = item.get("metric", {}).get("container", "unknown")
                try:
                    val = float(item.get("value", [0, 0])[1])
                except (ValueError, TypeError):
                    val = 0.0
                results.setdefault(name, {"cpu_pct": 0.0, "mem_mb": 0.0})
                results[name]["cpu_pct"] = val

        if r_mem.status_code == 200:
            for item in r_mem.json().get("data", {}).get("result", []):
                name = item.get("metric", {}).get("container", "unknown")
                try:
                    val = float(item.get("value", [0, 0])[1]) / (1024 * 1024)
                except (ValueError, TypeError):
                    val = 0.0
                results.setdefault(name, {"cpu_pct": 0.0, "mem_mb": 0.0})
                results[name]["mem_mb"] = val

    except Exception as e:
        print(f"[Proactive] Container metrics error: {e}")

    return results


def _fetch_pgbouncer_metrics(prometheus_ip: str, prometheus_port: str, projects: list) -> dict:
    """Returns {database: {waiting, active}} from Prometheus PgBouncer metrics."""
    results = {}
    if not prometheus_ip or not projects:
        return results

    base = f"http://{prometheus_ip}:{prometheus_port}/api/v1/query"
    safe_projects = [p for p in projects if _SAFE_PROJECT_NAME.match(str(p))]
    if not safe_projects:
        return results

    pgb_jobs = "|".join([f"{p}-pgbouncer-prod" for p in safe_projects])
    wait_q = f'sum(pgbouncer_pools_client_waiting_connections{{job=~"{pgb_jobs}"}}) by (database)'
    act_q  = f'sum(pgbouncer_pools_client_active_connections{{job=~"{pgb_jobs}"}}) by (database)'

    try:
        r_wait = requests.get(base, params={"query": wait_q}, timeout=8)
        r_act  = requests.get(base, params={"query": act_q}, timeout=8)

        if r_wait.status_code == 200:
            for item in r_wait.json().get("data", {}).get("result", []):
                db = item.get("metric", {}).get("database", "unknown")
                try:
                    val = float(item.get("value", [0, 0])[1])
                except (ValueError, TypeError):
                    val = 0.0
                results.setdefault(db, {"waiting": 0.0, "active": 0.0})
                results[db]["waiting"] = val

        if r_act.status_code == 200:
            for item in r_act.json().get("data", {}).get("result", []):
                db = item.get("metric", {}).get("database", "unknown")
                try:
                    val = float(item.get("value", [0, 0])[1])
                except (ValueError, TypeError):
                    val = 0.0
                results.setdefault(db, {"waiting": 0.0, "active": 0.0})
                results[db]["active"] = val

    except Exception as e:
        print(f"[Proactive] PgBouncer metrics error: {e}")

    return results


def _fetch_springboot_actuator_metrics(prometheus_ip: str, prometheus_port: str, projects: list) -> dict:
    """
    Returns {app_name: {hikari_active, hikari_pending, hikari_max, jvm_heap_pct, gc_pause_max_s, tomcat_busy}}
    from Prometheus metrics scraped from Spring Boot Actuator.
    """
    results = {}
    if not prometheus_ip or not projects:
        return results

    base = f"http://{prometheus_ip}:{prometheus_port}/api/v1/query"
    safe_projects = [p for p in projects if _SAFE_PROJECT_NAME.match(str(p))]
    if not safe_projects:
        return results

    app_jobs = "|".join([f"{p}-*" for p in safe_projects] + [f"{p}" for p in safe_projects])

    hikari_pend_q = f'sum(hikaricp_connections_pending{{job=~"{app_jobs}"}}) by (job)'
    hikari_act_q  = f'sum(hikaricp_connections_active{{job=~"{app_jobs}"}}) by (job)'
    hikari_max_q  = f'sum(hikaricp_connections_max{{job=~"{app_jobs}"}}) by (job)'
    jvm_heap_q = (
        f'sum(jvm_memory_used_bytes{{job=~"{app_jobs}", area="heap"}}) by (job) / '
        f'sum(jvm_memory_max_bytes{{job=~"{app_jobs}", area="heap"}}) by (job) * 100'
    )
    jvm_gc_q = f'max(jvm_gc_pause_seconds_max{{job=~"{app_jobs}"}}) by (job)'
    tomcat_busy_q = f'sum(tomcat_threads_busy_threads{{job=~"{app_jobs}"}}) by (job)'

    def _query_prom(q):
        try:
            r = requests.get(base, params={"query": q}, timeout=6)
            if r.status_code == 200:
                return r.json().get("data", {}).get("result", [])
        except Exception as e:
            print(f"[Proactive] Spring Boot Actuator metric query error: {e}")
        return []

    for item in _query_prom(hikari_pend_q):
        job = item.get("metric", {}).get("job", "springboot")
        val = float(item.get("value", [0, 0])[1] or 0)
        results.setdefault(job, {"hikari_pending": 0, "hikari_active": 0, "hikari_max": 0, "jvm_heap_pct": 0.0, "gc_pause_max_s": 0.0, "tomcat_busy": 0})
        results[job]["hikari_pending"] = int(val)

    for item in _query_prom(hikari_act_q):
        job = item.get("metric", {}).get("job", "springboot")
        val = float(item.get("value", [0, 0])[1] or 0)
        results.setdefault(job, {"hikari_pending": 0, "hikari_active": 0, "hikari_max": 0, "jvm_heap_pct": 0.0, "gc_pause_max_s": 0.0, "tomcat_busy": 0})
        results[job]["hikari_active"] = int(val)

    for item in _query_prom(hikari_max_q):
        job = item.get("metric", {}).get("job", "springboot")
        val = float(item.get("value", [0, 0])[1] or 0)
        results.setdefault(job, {"hikari_pending": 0, "hikari_active": 0, "hikari_max": 0, "jvm_heap_pct": 0.0, "gc_pause_max_s": 0.0, "tomcat_busy": 0})
        results[job]["hikari_max"] = int(val)

    for item in _query_prom(jvm_heap_q):
        job = item.get("metric", {}).get("job", "springboot")
        val = float(item.get("value", [0, 0])[1] or 0)
        results.setdefault(job, {"hikari_pending": 0, "hikari_active": 0, "hikari_max": 0, "jvm_heap_pct": 0.0, "gc_pause_max_s": 0.0, "tomcat_busy": 0})
        results[job]["jvm_heap_pct"] = round(val, 1)

    for item in _query_prom(jvm_gc_q):
        job = item.get("metric", {}).get("job", "springboot")
        val = float(item.get("value", [0, 0])[1] or 0)
        results.setdefault(job, {"hikari_pending": 0, "hikari_active": 0, "hikari_max": 0, "jvm_heap_pct": 0.0, "gc_pause_max_s": 0.0, "tomcat_busy": 0})
        results[job]["gc_pause_max_s"] = round(val, 2)

    for item in _query_prom(tomcat_busy_q):
        job = item.get("metric", {}).get("job", "springboot")
        val = float(item.get("value", [0, 0])[1] or 0)
        results.setdefault(job, {"hikari_pending": 0, "hikari_active": 0, "hikari_max": 0, "jvm_heap_pct": 0.0, "gc_pause_max_s": 0.0, "tomcat_busy": 0})
        results[job]["tomcat_busy"] = int(val)

    return results


def _fetch_node_resource_metrics(prometheus_ip: str, prometheus_port: str) -> dict:
    """
    Fetches real-time Node CPU %, Memory %, and Disk Read/Write MB/s from Prometheus Node Exporter.
    Returns { ip_or_instance: { instance, nodename, cpu_pct, mem_pct, disk_read_mb, disk_write_mb } }
    """
    results = {}
    if not prometheus_ip:
        return results

    base = f"http://{prometheus_ip}:{prometheus_port}/api/v1/query"

    def _query(promql):
        try:
            r = requests.get(base, params={"query": promql}, timeout=3)
            if r.status_code == 200:
                return r.json().get("data", {}).get("result", [])
        except Exception:
            pass
        return []

    # 1. Node Info
    for row in _query("node_uname_info"):
        m = row.get("metric", {})
        raw_inst = m.get("instance", "")
        inst_ip = raw_inst.split(":")[0] if ":" in raw_inst else raw_inst
        nodename = m.get("nodename", inst_ip)
        if inst_ip:
            results[inst_ip] = {
                "instance": inst_ip,
                "raw_instance": raw_inst,
                "nodename": nodename,
                "cpu_pct": 0.0,
                "mem_pct": 0.0,
                "disk_read_mb": 0.0,
                "disk_write_mb": 0.0
            }

    # 2. CPU Usage %
    for row in _query('100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)'):
        raw_inst = row.get("metric", {}).get("instance", "")
        inst_ip = raw_inst.split(":")[0] if ":" in raw_inst else raw_inst
        if inst_ip in results:
            try: results[inst_ip]["cpu_pct"] = round(float(row["value"][1]), 1)
            except: pass

    # 3. Memory Usage %
    for row in _query('(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'):
        raw_inst = row.get("metric", {}).get("instance", "")
        inst_ip = raw_inst.split(":")[0] if ":" in raw_inst else raw_inst
        if inst_ip in results:
            try: results[inst_ip]["mem_pct"] = round(float(row["value"][1]), 1)
            except: pass

    # 4. Disk Read MB/s
    for row in _query('sum by (instance) (rate(node_disk_read_bytes_total[2m])) / 1048576'):
        raw_inst = row.get("metric", {}).get("instance", "")
        inst_ip = raw_inst.split(":")[0] if ":" in raw_inst else raw_inst
        if inst_ip in results:
            try: results[inst_ip]["disk_read_mb"] = round(float(row["value"][1]), 2)
            except: pass

    # 5. Disk Write MB/s
    for row in _query('sum by (instance) (rate(node_disk_written_bytes_total[2m])) / 1048576'):
        raw_inst = row.get("metric", {}).get("instance", "")
        inst_ip = raw_inst.split(":")[0] if ":" in raw_inst else raw_inst
        if inst_ip in results:
            try: results[inst_ip]["disk_write_mb"] = round(float(row["value"][1]), 2)
            except: pass

    return results



def _explain_query_plan(cur, query_text: str) -> dict:
    """
    Automated EXPLAIN Plan Analysis.
    Safely inspects execution plan for SELECT queries to detect Seq Scans, High Cost, or Disk Spills.
    """
    if not query_text:
        return {"can_explain": False, "reason": "Empty query"}

    cleaned = query_text.strip()
    if cleaned.startswith("/*"):
        comment_end = cleaned.find("*/")
        if comment_end != -1:
            cleaned = cleaned[comment_end + 2:].strip()

    upper = cleaned.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return {"can_explain": False, "reason": "Non-SELECT query skipped for safety"}

    try:
        cur.execute(f"EXPLAIN (FORMAT JSON) {cleaned}")
        raw_plan = cur.fetchone()
        if not raw_plan:
            return {"can_explain": False, "reason": "Empty plan"}

        plan_data = raw_plan[0] if isinstance(raw_plan[0], list) else raw_plan
        plan_node = plan_data[0].get("Plan", {}) if isinstance(plan_data, list) and plan_data else {}

        seq_scans = []
        def _walk_plan(node):
            if not isinstance(node, dict):
                return
            n_type = node.get("Node Type", "")
            rel = node.get("Relation Name", "")
            if n_type == "Seq Scan" and rel:
                seq_scans.append(rel)
            for child in node.get("Plans", []):
                _walk_plan(child)

        _walk_plan(plan_node)
        return {
            "can_explain": True,
            "total_cost": round(float(plan_node.get("Total Cost", 0.0)), 1),
            "node_type": plan_node.get("Node Type", "Unknown"),
            "seq_scans": list(set(seq_scans)),
            "has_seq_scan": len(seq_scans) > 0
        }
    except Exception as e:
        return {"can_explain": False, "reason": f"EXPLAIN failed: {type(e).__name__}"}


def _extract_trace_ids_from_loki(loki_ip: str, projects: list, window_minutes: int = 5) -> list:
    """
    Extracts active Trace IDs & Request IDs from Loki logs (W3C traceparent, trace_id, x_request_id).
    """
    if not loki_ip or not projects:
        return []

    safe_projects = [p for p in projects if _SAFE_PROJECT_NAME.match(str(p))]
    if not safe_projects:
        return []

    projects_regex = "|".join(safe_projects)
    query = f'{{project=~"{projects_regex}"}}'
    now_ns = int(time.time() * 1_000_000_000)
    start_ns = now_ns - (window_minutes * 60 * 1_000_000_000)

    trace_pattern = re.compile(r'(?:traceparent|trace_id|x_request_id|request_id)=([a-zA-Z0-9_-]{8,64})', re.IGNORECASE)
    found_traces = []

    try:
        resp = requests.get(
            f"http://{loki_ip}:3100/loki/api/v1/query_range",
            params={"query": query, "limit": 200, "start": start_ns, "end": now_ns},
            timeout=6
        )
        if resp.status_code == 200:
            for stream in resp.json().get("data", {}).get("result", []):
                for _, log_line in stream.get("values", []):
                    matches = trace_pattern.findall(log_line)
                    for m in matches:
                        if m not in found_traces:
                            found_traces.append(m)
                            if len(found_traces) >= 10:
                                break
    except Exception as e:
        print(f"[Proactive] Trace ID extraction from Loki error: {e}")

    return found_traces


def _fetch_db_health(db_connections_json_str: str) -> list:
    """Direct DB: long-running queries + connection saturation."""
    results = []
    if not db_connections_json_str:
        return results

    try:
        conns = json.loads(db_connections_json_str)
    except Exception:
        return results

    try:
        import psycopg2
    except ImportError:
        print("[Proactive] psycopg2 not available, skipping DB health check")
        return results

    for conn_info in conns:
        label    = conn_info.get("label", conn_info.get("host", "DB"))
        host     = conn_info.get("host")
        port     = conn_info.get("port", 5432)
        dbname   = conn_info.get("dbname")
        user     = conn_info.get("user")
        password = conn_info.get("password")

        if not all([host, dbname, user, password]):
            continue

        entry = {
            "label": label, "long_queries": [], "wait_summary": [],
            "conn_active": 0, "conn_max": 0, "conn_pct": 0.0, "error": None
        }
        conn = None
        try:
            conn = psycopg2.connect(
                host=host, port=int(port), dbname=dbname,
                user=user, password=password, connect_timeout=3
            )
            cur = conn.cursor()

            # 1. Long-running queries + wait events + blocking PIDs
            try:
                cur.execute("""
                    SELECT pid, state, wait_event_type, wait_event,
                           pg_blocking_pids(pid) AS blocking_pids,
                           ROUND(EXTRACT(epoch FROM (now() - query_start))) AS dur,
                           SUBSTRING(query FROM 1 FOR 150) AS q
                    FROM pg_stat_activity
                    WHERE state != 'idle' AND pid != pg_backend_pid()
                      AND backend_type != 'walsender'
                      AND query NOT ILIKE 'START_REPLICATION%'
                      AND query NOT ILIKE 'autovacuum:%'
                      AND query_start IS NOT NULL
                      AND EXTRACT(epoch FROM (now() - query_start)) > %s
                    ORDER BY dur DESC LIMIT 5
                """, (THRESHOLDS["long_query_warn_s"],))
                raw_rows = cur.fetchall()
                l_queries = []
                for r in raw_rows:
                    pid, state, wait_type, wait_ev, blocking, dur, q_text = r[0], r[1], r[2], r[3], r[4], r[5], (r[6] or "").strip()
                    plan_info = _explain_query_plan(cur, q_text)
                    l_queries.append({
                        "pid": pid,
                        "state": state,
                        "wait_event_type": wait_type,
                        "wait_event": wait_ev,
                        "blocking_pids": [int(p) for p in (blocking or [])],
                        "duration_sec": int(dur or 0),
                        "query": q_text,
                        "explain_plan": plan_info
                    })
                entry["long_queries"] = l_queries
            except Exception as e:
                conn.rollback()

            # 2. Wait Event Breakdown across active backends
            try:
                cur.execute("""
                    SELECT COALESCE(wait_event_type, 'Executing/CPU') AS wait_type,
                           COALESCE(wait_event, 'Active') AS wait_event,
                           count(*) AS cnt
                    FROM pg_stat_activity
                    WHERE state != 'idle' AND pid != pg_backend_pid()
                    GROUP BY wait_event_type, wait_event
                    ORDER BY count(*) DESC LIMIT 5
                """)
                entry["wait_summary"] = [
                    {"wait_type": r[0], "wait_event": r[1], "count": int(r[2])}
                    for r in cur.fetchall()
                ]
            except Exception as e:
                conn.rollback()

            # 3. Connection count vs max
            try:
                cur.execute("SELECT count(*) FROM pg_stat_activity WHERE state != 'idle'")
                entry["conn_active"] = cur.fetchone()[0] or 0
                cur.execute("SHOW max_connections")
                entry["conn_max"] = int(cur.fetchone()[0] or 100)
                entry["conn_pct"] = (entry["conn_active"] / entry["conn_max"] * 100) if entry["conn_max"] > 0 else 0.0
            except Exception as e:
                conn.rollback()

            cur.close()
        except Exception as e:
            entry["error"] = f"Cannot connect to {label}"
            print(f"[Proactive] DB connect error {label}: {type(e).__name__}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        results.append(entry)

    return results


def _fetch_loki_error_rate(loki_ip: str, projects: list, window_minutes: int = 5) -> int:
    """Count error/5xx log entries from Loki in the last N minutes."""
    if not loki_ip or not projects:
        return 0

    safe_projects = [p for p in projects if _SAFE_PROJECT_NAME.match(str(p))]
    if not safe_projects:
        return 0

    projects_regex = "|".join(safe_projects)
    query = f'{{project=~"{projects_regex}", environment="production"}}'
    now_ns = int(time.time() * 1_000_000_000)
    start_ns = now_ns - (window_minutes * 60 * 1_000_000_000)

    try:
        resp = requests.get(
            f"http://{loki_ip}:3100/loki/api/v1/query_range",
            params={"query": query, "limit": 500, "start": start_ns, "end": now_ns},
            timeout=8
        )
        if resp.status_code != 200:
            return 0
        count = 0
        for stream in resp.json().get("data", {}).get("result", []):
            for _, log_line in stream.get("values", []):
                lower = log_line.lower()
                if any(kw in lower for kw in ["error", "status=5", " 500 ", " 502 ", " 503 ", " 504 "]):
                    count += 1
        return count
    except Exception as e:
        print(f"[Proactive] Loki error rate fetch failed: {e}")
        return 0


# ─────────────────────────────────────────────────
# Health Score Computation
# ─────────────────────────────────────────────────

def compute_health_score(container_metrics: dict, pgb_metrics: dict, db_health: list, error_count: int, springboot_metrics: dict = None) -> tuple:
    """Compute health score (0-100), list of alerts, and status string."""
    score = 100
    alerts = []
    springboot_metrics = springboot_metrics or {}

    # Spring Boot Actuator (HikariCP, JVM Heap, GC Pause)
    for app_name, sb in springboot_metrics.items():
        pending = sb.get("hikari_pending", 0)
        active = sb.get("hikari_active", 0)
        max_conn = sb.get("hikari_max", 0)
        heap_pct = sb.get("jvm_heap_pct", 0.0)
        gc_pause = sb.get("gc_pause_max_s", 0.0)

        if pending >= THRESHOLDS["hikari_pending_crit"]:
            score -= 30
            alerts.append(f"🔴 CRITICAL: Spring Boot [{app_name}] HikariCP Pool SATURATED! {pending} threads waiting for connection (Active: {active}/{max_conn})")
        elif pending >= THRESHOLDS["hikari_pending_warn"]:
            score -= 15
            alerts.append(f"🟡 WARNING: Spring Boot [{app_name}] HikariCP Pool Queue: {pending} threads waiting for DB connection")

        if heap_pct >= THRESHOLDS["jvm_heap_crit"]:
            score -= 25
            alerts.append(f"🔴 CRITICAL: Spring Boot [{app_name}] JVM Heap Memory at {heap_pct:.1f}% (High risk of OutOfMemoryError / GC Thrashing)")
        elif heap_pct >= THRESHOLDS["jvm_heap_warn"]:
            score -= 10
            alerts.append(f"🟡 WARNING: Spring Boot [{app_name}] JVM Heap Memory at {heap_pct:.1f}%")

        if gc_pause >= THRESHOLDS["jvm_gc_pause_crit_s"]:
            score -= 25
            alerts.append(f"🔴 CRITICAL: Spring Boot [{app_name}] JVM GC Stop-The-World Pause = {gc_pause:.2f}s (Application Freeze)")
        elif gc_pause >= THRESHOLDS["jvm_gc_pause_warn_s"]:
            score -= 10
            alerts.append(f"🟡 WARNING: Spring Boot [{app_name}] JVM GC Pause = {gc_pause:.2f}s")

    # Container CPU
    for name, m in container_metrics.items():
        cpu = m.get("cpu_pct", 0.0)
        if cpu >= THRESHOLDS["cpu_crit"]:
            score -= 25
            alerts.append(f"🔴 CRITICAL: Container [{name}] CPU = {cpu:.1f}% (threshold >{THRESHOLDS['cpu_crit']}%)")
        elif cpu >= THRESHOLDS["cpu_warn"]:
            score -= 10
            alerts.append(f"🟡 WARNING: Container [{name}] CPU = {cpu:.1f}% (threshold >{THRESHOLDS['cpu_warn']}%)")

    # PgBouncer Waiting Connections
    for db_name, p in pgb_metrics.items():
        waiting = p.get("waiting", 0.0)
        if waiting >= THRESHOLDS["pgb_wait_crit"]:
            score -= 30
            alerts.append(f"🔴 CRITICAL: PgBouncer [{db_name}] {int(waiting)} clients waiting (threshold >{THRESHOLDS['pgb_wait_crit']})")
        elif waiting >= THRESHOLDS["pgb_wait_warn"]:
            score -= 15
            alerts.append(f"🟡 WARNING: PgBouncer [{db_name}] {int(waiting)} clients waiting")
        elif waiting > 0:
            score -= 5
            alerts.append(f"🟠 NOTICE: PgBouncer [{db_name}] {int(waiting)} client waiting")

    # Long-running Queries + Lock Contention + Wait Events
    for entry in db_health:
        label = entry.get("label", "DB")
        for q in entry.get("long_queries", []):
            dur = q.get("duration_sec", 0)
            wait_type = q.get("wait_event_type")
            wait_ev = q.get("wait_event")
            blocking = q.get("blocking_pids", [])

            wait_str = ""
            if wait_type == "Lock":
                block_txt = f" (ติด LOCK โดย PID {blocking})" if blocking else " (ติด LOCK CONTENTION)"
                wait_str = block_txt
            elif wait_type == "IO":
                wait_str = f" (รอ DISK IO: {wait_ev})"
            elif wait_type:
                wait_str = f" (รอ {wait_type}/{wait_ev})"

            if dur >= THRESHOLDS["long_query_crit_s"]:
                score -= 35
                alerts.append(
                    f"🔴 CRITICAL: DB [{label}] PID {q['pid']} รัน {dur}s{wait_str} "
                    f"(state={q['state']}): {q['query'][:80]}..."
                )
            elif dur >= THRESHOLDS["long_query_warn_s"]:
                score -= 20
                alerts.append(
                    f"🟡 WARNING: DB [{label}] PID {q['pid']} รัน {dur}s{wait_str}: {q['query'][:80]}..."
                )

        # Wait Event Summary alerts (e.g., Multiple queries blocked by lock)
        for w in entry.get("wait_summary", []):
            if w["wait_type"] == "Lock" and w["count"] >= 2:
                score -= 15
                alerts.append(f"🔴 CRITICAL: DB [{label}] ตรวจพบ {w['count']} คิวรีค้างรอ LOCK ตาราง ({w['wait_event']})")
            elif w["wait_type"] == "IO" and w["count"] >= 3:
                score -= 10
                alerts.append(f"🟡 WARNING: DB [{label}] ตรวจพบ {w['count']} คิวรีค้างรอ DISK IO ({w['wait_event']})")

        conn_pct = entry.get("conn_pct", 0.0)
        conn_active = entry.get("conn_active", 0)
        conn_max = entry.get("conn_max", 0)
        if conn_pct >= THRESHOLDS["db_conn_crit_pct"]:
            score -= 20
            alerts.append(f"🔴 CRITICAL: DB [{label}] Connections {conn_active}/{conn_max} ({conn_pct:.0f}% of max_connections)")
        elif conn_pct >= THRESHOLDS["db_conn_warn_pct"]:
            score -= 10
            alerts.append(f"🟡 WARNING: DB [{label}] Connections {conn_active}/{conn_max} ({conn_pct:.0f}% of max_connections)")

    # Loki Error Rate
    if error_count >= THRESHOLDS["error_rate_crit"]:
        score -= 15
        alerts.append(f"🔴 CRITICAL: Loki Error/5xx count = {error_count} ใน 5 นาทีที่ผ่านมา")
    elif error_count >= THRESHOLDS["error_rate_warn"]:
        score -= 10
        alerts.append(f"🟡 WARNING: Loki Error/5xx count = {error_count} ใน 5 นาทีที่ผ่านมา")

    score = max(0, score)
    if score >= 80:
        status = "healthy"
    elif score >= 50:
        status = "warning"
    else:
        status = "critical"

    return score, alerts, status


# ─────────────────────────────────────────────────
# AI Full Diagnosis
# ─────────────────────────────────────────────────

def _call_ai_diagnosis(setting, alerts: list, container_metrics: dict, pgb_metrics: dict, db_health: list, error_count: int, springboot_metrics: dict = None) -> str:
    """Call AI for full root cause analysis when anomalies are detected."""
    provider  = getattr(setting, "ai_provider", "lmstudio") or "lmstudio"
    host_url  = getattr(setting, "ai_host_url", "") or ""
    model_name = getattr(setting, "ai_model_name", "") or ""
    springboot_metrics = springboot_metrics or {}

    if not host_url or not model_name:
        return "AI Provider ยังไม่ได้ตั้งค่า"

    api_url = f"{host_url.rstrip('/')}/chat/completions"
    is_ollama_native = (provider == "ollama" and "/v1" not in host_url and ":11434" in host_url)
    if is_ollama_native:
        api_url = f"{host_url.rstrip('/')}/api/chat"

    alert_text = "\n".join(alerts) if alerts else "ไม่มี Alert"

    container_text = "\n".join(
        f"- {name}: CPU={m.get('cpu_pct', 0):.2f}% | Memory={m.get('mem_mb', 0):.1f} MB"
        for name, m in container_metrics.items()
    ) or "ไม่มีข้อมูล"

    pgb_text = "\n".join(
        f"- {db}: Active={p.get('active', 0):.0f} | Waiting={p.get('waiting', 0):.0f}"
        for db, p in pgb_metrics.items()
    ) or "ไม่มีข้อมูล"

    springboot_text = "\n".join(
        f"- {app}: Hikari Active={m.get('hikari_active',0)}/{m.get('hikari_max',0)} | Hikari Pending Queue={m.get('hikari_pending',0)} | JVM Heap={m.get('jvm_heap_pct',0):.1f}% | GC Pause Max={m.get('gc_pause_max_s',0):.2f}s | Tomcat Threads Busy={m.get('tomcat_busy',0)}"
        for app, m in springboot_metrics.items()
    ) or "ไม่มีข้อมูล"

    try:
        projects = json.loads(setting.loki_projects)
    except Exception:
        projects = []

    traces = _extract_trace_ids_from_loki(setting.loki_ip, projects, window_minutes=5)
    trace_text = ", ".join(traces) if traces else "ไม่พบ Trace ID ค้างใน Logs"

    db_text = ""
    for entry in db_health:
        db_text += f"- {entry['label']}: Connections {entry['conn_active']}/{entry['conn_max']} ({entry['conn_pct']:.0f}%)\n"
        for w in entry.get("wait_summary", []):
            db_text += f"  - Wait Event Breakdown: {w['wait_type']} / {w['wait_event']} ({w['count']} connections)\n"
        for q in entry.get("long_queries", []):
            wait_info = f" [Wait: {q.get('wait_event_type')}/{q.get('wait_event')}]" if q.get("wait_event_type") else ""
            block_info = f" ⛔ BLOCKED by PID {q.get('blocking_pids')}" if q.get("blocking_pids") else ""
            exp_info = ""
            exp = q.get("explain_plan", {})
            if exp.get("has_seq_scan"):
                exp_info = f" ⚠️ [EXPLAIN: Seq Scan on {exp.get('seq_scans')}, Cost={exp.get('total_cost')}]"
            elif exp.get("can_explain"):
                exp_info = f" [EXPLAIN: {exp.get('node_type')}, Cost={exp.get('total_cost')}]"
            db_text += f"  - Long Query: PID {q['pid']} [{q['state']}]{wait_info}{block_info}{exp_info} {q['duration_sec']}s: {q['query'][:150]}\n"
    db_text = db_text or "ไม่มีข้อมูล"

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    system_prompt = (
        "คุณคือ Senior DevOps Engineer และ DBA ผู้เชี่ยวชาญด้านระบบ WMS/TMS บน PostgreSQL + PgBouncer + Spring Boot "
        "หน้าที่ของคุณคือรับข้อมูล Proactive Health Alert แบบ Real-time และวิเคราะห์ Root Cause พร้อมให้คำแนะนำทันที\n\n"
        "กฎเหล็ก: ห้ามใช้ HTML แท็กทุกชนิด (<br>, <b> ฯลฯ) Output ต้องเป็น Pure Markdown เท่านั้น"
    )
    user_prompt = f"""ระบบ WMS/TMS ตรวจพบ Anomaly ณ เวลา {now_str}

## Alerts ที่ตรวจพบ:
{alert_text}

## Container Resource (Prometheus cAdvisor):
{container_text}

## Spring Boot Actuator (JVM & HikariCP Pool):
{springboot_text}

## PgBouncer Connection Pool (Prometheus):
{pgb_text}

## Direct DB Status & Automated EXPLAIN Plan Analysis (pg_stat_activity):
{db_text}

## Distributed Trace ID Correlations (Loki ↔ DB):
{trace_text}

## Loki Error Count (5 นาทีล่าสุด): {error_count} รายการ

---

จงวิเคราะห์และตอบในรูปแบบนี้:

## Root Cause Analysis
(อธิบาย chain of events ที่ทำให้เกิดปัญหา)

## Immediate Actions (ทำได้ทันที ภายใน 5 นาที)
(คำสั่ง/ขั้นตอนที่ต้องทำตอนนี้เลย)

## Root Cause Fix (แก้ที่ต้นเหตุ)
(วิธีแก้ถาวร พร้อมพาธ Config และคำสั่ง)

## Prevention (ป้องกันระยะยาว)
(แนวทาง Architecture/Config ที่ควรปรับ)"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    if is_ollama_native:
        payload = {"model": model_name, "messages": messages, "options": {"temperature": 0.1}, "stream": False}
    else:
        payload = {"model": model_name, "messages": messages, "temperature": 0.1, "stream": False}

    try:
        resp = requests.post(api_url, json=payload, timeout=600)
        if resp.status_code == 200:
            data = resp.json()
            if is_ollama_native:
                return data.get("message", {}).get("content", "No response from Ollama")
            choices = data.get("choices", [])
            if not choices:
                return "AI returned empty response"
            return choices[0].get("message", {}).get("content", "No content in AI response")
        return f"AI API Error: {resp.status_code}"
    except Exception as e:
        return f"ไม่สามารถเชื่อมต่อ AI: {type(e).__name__}"


# ─────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────

def run_proactive_health_check(setting, db_session, redis_url: str) -> dict:
    """
    Main proactive health check runner.
    Called by the scheduler every N minutes (configurable via setting.proactive_interval_minutes).
    """
    from .models import HealthEvent

    print(f"[Proactive] Health check at {datetime.now().strftime('%H:%M:%S')}...")

    try:
        projects = json.loads(setting.loki_projects)
    except Exception:
        projects = []

    # 1. Collect lightweight metrics
    container_metrics  = _fetch_container_metrics(setting.prometheus_ip, setting.prometheus_port, projects)
    pgb_metrics        = _fetch_pgbouncer_metrics(setting.prometheus_ip, setting.prometheus_port, projects)
    springboot_metrics = _fetch_springboot_actuator_metrics(setting.prometheus_ip, setting.prometheus_port, projects)
    db_health          = _fetch_db_health(getattr(setting, "db_connections_json", None) or "")
    error_count        = _fetch_loki_error_rate(setting.loki_ip, projects, window_minutes=5)

    # 2. Compute score
    score, alerts, status = compute_health_score(container_metrics, pgb_metrics, db_health, error_count, springboot_metrics)
    print(f"[Proactive] Score: {score} | Status: {status} | Alerts: {len(alerts)}")

    metrics_snapshot = {
        "containers": container_metrics,
        "pgbouncer": pgb_metrics,
        "springboot": springboot_metrics,
        "db_health": [
            {"label": e["label"], "conn_active": e["conn_active"],
             "conn_max": e["conn_max"], "conn_pct": round(e["conn_pct"], 1),
             "long_query_count": len(e.get("long_queries", []))}
            for e in db_health
        ],
        "loki_error_count_5m": error_count
    }

    # 3. AI + Discord on anomaly (with debounce)
    ai_diagnosis = None
    if alerts:
        r = _get_redis(redis_url)
        alert_key = f"score_bucket_{score // 10 * 10}"  # debounce per 10-point score bucket

        if not _is_debounced(r, alert_key):
            print(f"[Proactive] Calling AI for diagnosis...")
            ai_diagnosis = _call_ai_diagnosis(
                setting, alerts, container_metrics, pgb_metrics, db_health, error_count, springboot_metrics
            )
            _set_debounce(r, alert_key)

            if getattr(setting, "proactive_discord_enabled", True) and setting.discord_webhook_url:
                try:
                    from .notifier import send_discord_alert
                    score_emoji = "🔴" if status == "critical" else "🟡" if status == "warning" else "🟢"
                    title = f"{score_emoji} Proactive Alert — Health Score {score}/100 ({status.upper()})"
                    discord_body = (
                        f"**Anomalies ({len(alerts)} alerts):**\n"
                        + "\n".join(alerts[:5])
                        + (f"\n...+{len(alerts)-5} more" if len(alerts) > 5 else "")
                        + "\n\n---\n"
                        + (ai_diagnosis[:2500] if ai_diagnosis else "")
                    )
                    color = 15548997 if status == "critical" else 16776960 if status == "warning" else 5763719
                    send_discord_alert(setting.discord_webhook_url, title, discord_body[:4096], color=color)
                except Exception as e:
                    print(f"[Proactive] Discord alert failed: {e}")
        else:
            print(f"[Proactive] Debounced — same score bucket sent recently")

    # 4. Always save HealthEvent to DB
    try:
        event = HealthEvent(
            health_score=score,
            status=status,
            alerts_json=json.dumps(alerts, ensure_ascii=False) if alerts else None,
            metrics_json=json.dumps(metrics_snapshot, ensure_ascii=False),
            ai_diagnosis=ai_diagnosis
        )
        db_session.add(event)
        db_session.commit()
    except Exception as e:
        print(f"[Proactive] Failed to save HealthEvent: {e}")
        try:
            db_session.rollback()
        except Exception:
            pass

    return {"health_score": score, "status": status, "alert_count": len(alerts), "ai_called": ai_diagnosis is not None}

