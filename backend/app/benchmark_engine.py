import asyncio
import time
import json
import math
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Dict, List, Optional
import psycopg2

class BenchmarkEngine:
    """
    Asynchronous Benchmark Engine for HTTP APIs and Direct PostgreSQL Queries.
    Calculates real-time RPS/QPS, latency percentiles (p50/p90/p95/p99),
    and requests AI Performance Optimization Analysis upon test completion.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.is_running = False
        self.should_stop = False
        self.name = "Benchmark Run"
        self.mode = "http"  # 'http' or 'postgres'
        self.target_summary = ""
        self.target_sql = None
        self.target_db_info = None
        self.target_url = None
        self.target_method = None
        self.concurrent_users = 10
        self.duration_seconds = 15
        self.start_time = 0.0
        self.elapsed_seconds = 0.0

        self.total_ops = 0
        self.success_ops = 0
        self.failed_ops = 0

        self.latencies_ms: List[float] = []
        self.status_codes: Dict[str, int] = {}
        self.timeline: List[dict] = []  # per-second snapshot records

        self.current_rps = 0.0
        self.current_avg_ms = 0.0
        self.current_p99_ms = 0.0
        self.current_error_rate = 0.0

        self.last_completed_report_id = None
        self.last_error = None

    def get_live_status(self) -> dict:
        """Returns live execution status snapshot for dashboard UI."""
        elapsed = time.time() - self.start_time if self.is_running else self.elapsed_seconds
        remaining = max(0, self.duration_seconds - int(elapsed)) if self.is_running else 0
        progress_pct = min(100.0, (elapsed / self.duration_seconds) * 100.0) if self.duration_seconds > 0 else 0.0

        return {
            "is_running": self.is_running,
            "name": self.name,
            "mode": self.mode,
            "target_summary": self.target_summary,
            "concurrent_users": self.concurrent_users,
            "duration_seconds": self.duration_seconds,
            "elapsed_seconds": round(elapsed, 1),
            "remaining_seconds": remaining,
            "progress_pct": round(progress_pct, 1),
            "total_operations": self.total_ops,
            "success_operations": self.success_ops,
            "failed_operations": self.failed_ops,
            "current_ops_per_sec": round(self.current_rps, 1),
            "current_avg_ms": round(self.current_avg_ms, 1),
            "current_p99_ms": round(self.current_p99_ms, 1),
            "current_error_rate": round(self.current_error_rate, 1),
            "last_completed_report_id": self.last_completed_report_id,
            "last_error": self.last_error
        }

    def stop(self):
        """Signals the benchmark run to stop early."""
        if self.is_running:
            self.should_stop = True

    async def run_http_benchmark(
        self,
        name: str,
        target_url: str,
        method: str,
        headers_json: Optional[str],
        payload_json: Optional[str],
        concurrent_users: int,
        duration_seconds: int,
        setting,
        db_session
    ):
        """Executes asynchronous HTTP Load/Stress test."""
        import httpx

        self.is_running = True
        self.should_stop = False
        self.name = name or "HTTP Benchmark"
        self.mode = "http"
        self.target_summary = f"{method.upper()} {target_url}"
        self.target_url = target_url
        self.target_method = method
        self.target_sql = None
        self.target_db_info = None
        self.concurrent_users = max(1, min(1000, concurrent_users))
        self.duration_seconds = max(3, min(300, duration_seconds))
        self.start_time = time.time()

        self.total_ops = 0
        self.success_ops = 0
        self.failed_ops = 0
        self.latencies_ms = []
        self.status_codes = {}
        self.timeline = []
        self.last_error = None

        sampler_task = None
        try:
            headers = json.loads(headers_json) if headers_json else {}
            payload = json.loads(payload_json) if payload_json else None

            end_time = self.start_time + self.duration_seconds

            async def _worker(client: httpx.AsyncClient):
                while time.time() < end_time and not self.should_stop:
                    t0 = time.perf_counter()
                    try:
                        res = await client.request(
                            method=method.upper(),
                            url=target_url,
                            headers=headers,
                            json=payload,
                            timeout=10.0
                        )
                        latency = (time.perf_counter() - t0) * 1000.0
                        status_code = res.status_code
                        code_str = str(status_code)

                        self.total_ops += 1
                        self.status_codes[code_str] = self.status_codes.get(code_str, 0) + 1
                        self.latencies_ms.append(latency)

                        if 200 <= status_code < 400:
                            self.success_ops += 1
                        else:
                            self.failed_ops += 1
                    except Exception as e:
                        latency = (time.perf_counter() - t0) * 1000.0
                        self.total_ops += 1
                        self.failed_ops += 1
                        err_str = type(e).__name__
                        self.status_codes[err_str] = self.status_codes.get(err_str, 0) + 1
                        self.latencies_ms.append(latency)

                    # Yield control briefly
                    await asyncio.sleep(0.001)

            async def _sampler():
                last_ops = 0
                while self.is_running and not self.should_stop:
                    await asyncio.sleep(1.0)
                    curr_time = time.time()
                    elapsed = curr_time - self.start_time
                    if elapsed <= 0:
                        continue

                    recent_ops = self.total_ops - last_ops
                    last_ops = self.total_ops

                    self.current_rps = float(recent_ops)
                    self.current_error_rate = (self.failed_ops / max(1, self.total_ops)) * 100.0

                    if self.latencies_ms:
                        sorted_lats = sorted(self.latencies_ms[-500:])  # last 500 samples
                        self.current_avg_ms = sum(sorted_lats) / len(sorted_lats)
                        p99_idx = max(0, int(math.ceil(0.99 * len(sorted_lats))) - 1)
                        self.current_p99_ms = sorted_lats[p99_idx]

                    self.timeline.append({
                        "second": int(elapsed),
                        "ops": recent_ops,
                        "avg_ms": round(self.current_avg_ms, 1),
                        "p99_ms": round(self.current_p99_ms, 1),
                        "failed": self.failed_ops
                    })

            # Run client workers
            sampler_task = asyncio.create_task(_sampler())
            limits = httpx.Limits(max_keepalive_connections=self.concurrent_users, max_connections=self.concurrent_users * 2)
            async with httpx.AsyncClient(limits=limits, verify=False) as client:
                workers = [_worker(client) for _ in range(self.concurrent_users)]
                await asyncio.gather(*workers)
        except Exception as e:
            self.last_error = str(e)
            print(f"[Benchmark] HTTP Benchmark error: {e}")
        finally:
            self.is_running = False
            self.elapsed_seconds = time.time() - self.start_time
            if sampler_task:
                sampler_task.cancel()

        # Compute final report
        await self._finish_and_save_report(setting, db_session)

    async def run_postgres_benchmark(
        self,
        name: str,
        db_conn_info: dict,
        sql_query: str,
        concurrent_users: int,
        duration_seconds: int,
        setting,
        db_session
    ):
        """Executes concurrent PostgreSQL Query Load/Stress test."""
        self.is_running = True
        self.should_stop = False
        self.name = name or "PostgreSQL Benchmark"
        self.mode = "postgres"
        db_label = db_conn_info.get("label", db_conn_info.get("host", "PostgreSQL"))
        cleaned_sql = sql_query.strip().replace('\n', ' ')[:100]
        self.target_summary = f"[{db_label}] {cleaned_sql}"
        self.target_sql = sql_query
        self.target_db_info = db_conn_info
        self.target_url = None
        self.target_method = None
        self.concurrent_users = max(1, min(1000, concurrent_users))
        self.duration_seconds = max(3, min(300, duration_seconds))
        self.start_time = time.time()

        self.total_ops = 0
        self.success_ops = 0
        self.failed_ops = 0
        self.latencies_ms = []
        self.status_codes = {}
        self.timeline = []
        self.last_error = None

        end_time = self.start_time + self.duration_seconds

        sampler_task = None
        try:
            def _db_worker_func():
                conn = None
                try:
                    conn = psycopg2.connect(
                        host=db_conn_info.get("host"),
                        port=int(db_conn_info.get("port", 5432)),
                        dbname=db_conn_info.get("dbname"),
                        user=db_conn_info.get("user"),
                        password=db_conn_info.get("password"),
                        connect_timeout=5
                    )
                    conn.autocommit = True
                    cur = conn.cursor()
                    cur.execute("SET statement_timeout = 30000; SET lock_timeout = 5000;")

                    while time.time() < end_time and not self.should_stop:
                        t0 = time.perf_counter()
                        try:
                            cur.execute(sql_query)
                            if cur.description is not None:
                                cur.fetchall()  # fetch result if query returns rows
                            lat = (time.perf_counter() - t0) * 1000.0

                            with self._lock:
                                self.total_ops += 1
                                self.success_ops += 1
                                self.latencies_ms.append(lat)
                                self.status_codes["OK"] = self.status_codes.get("OK", 0) + 1
                        except Exception as e:
                            if conn and not conn.autocommit:
                                try:
                                    conn.rollback()
                                except Exception:
                                    pass
                            lat = (time.perf_counter() - t0) * 1000.0
                            with self._lock:
                                self.total_ops += 1
                                self.failed_ops += 1
                                err_name = type(e).__name__
                                self.status_codes[err_name] = self.status_codes.get(err_name, 0) + 1
                                self.latencies_ms.append(lat)
                        time.sleep(0.001)
                    conn.close()
                except Exception as e:
                    self.last_error = f"Connection error: {e}"

            # Run DB workers in ThreadPool (capped at 64 to avoid OS thread exhaustion)
            loop = asyncio.get_running_loop()
            worker_pool_size = min(self.concurrent_users, 64)
            with ThreadPoolExecutor(max_workers=worker_pool_size) as executor:
                sampler_task = asyncio.create_task(self._async_sampler())
                futures = [loop.run_in_executor(executor, _db_worker_func) for _ in range(self.concurrent_users)]
                await asyncio.gather(*futures)
        except Exception as e:
            self.last_error = str(e)
            print(f"[Benchmark] Postgres Benchmark error: {e}")
        finally:
            self.is_running = False
            self.elapsed_seconds = time.time() - self.start_time
            if sampler_task:
                sampler_task.cancel()

        await self._finish_and_save_report(setting, db_session)

    async def _async_sampler(self):
        last_ops = 0
        while self.is_running and not self.should_stop:
            await asyncio.sleep(1.0)
            curr_time = time.time()
            elapsed = curr_time - self.start_time
            if elapsed <= 0:
                continue

            recent_ops = self.total_ops - last_ops
            last_ops = self.total_ops

            self.current_rps = float(recent_ops)
            self.current_error_rate = (self.failed_ops / max(1, self.total_ops)) * 100.0

            if self.latencies_ms:
                sorted_lats = sorted(self.latencies_ms[-500:])
                self.current_avg_ms = sum(sorted_lats) / len(sorted_lats)
                p99_idx = max(0, int(math.ceil(0.99 * len(sorted_lats))) - 1)
                self.current_p99_ms = sorted_lats[p99_idx]

            self.timeline.append({
                "second": int(elapsed),
                "ops": recent_ops,
                "avg_ms": round(self.current_avg_ms, 1),
                "p99_ms": round(self.current_p99_ms, 1),
                "failed": self.failed_ops
            })

    async def _finish_and_save_report(self, setting, db_session):
        """Computes final metrics, requests AI Analysis, and persists BenchmarkReport."""
        from .models import BenchmarkReport

        sorted_lats = sorted(self.latencies_ms) if self.latencies_ms else [0.0]
        n = len(sorted_lats)

        def _percentile(p: float) -> float:
            idx = max(0, int(math.ceil(p * n)) - 1)
            return sorted_lats[idx]

        min_ms = sorted_lats[0]
        max_ms = sorted_lats[-1]
        avg_ms = sum(sorted_lats) / n if n > 0 else 0.0
        p50_ms = _percentile(0.50)
        p90_ms = _percentile(0.90)
        p95_ms = _percentile(0.95)
        p99_ms = _percentile(0.99)

        ops_per_sec = self.total_ops / max(1.0, self.elapsed_seconds)

        report_summary = {
            "name": self.name,
            "mode": self.mode,
            "target_summary": self.target_summary,
            "target_sql": getattr(self, "target_sql", None),
            "target_db_info": getattr(self, "target_db_info", None),
            "target_url": getattr(self, "target_url", None),
            "target_method": getattr(self, "target_method", None),
            "concurrent_users": self.concurrent_users,
            "duration_seconds": self.duration_seconds,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "total_operations": self.total_ops,
            "success_operations": self.success_ops,
            "failed_operations": self.failed_ops,
            "ops_per_sec": round(ops_per_sec, 1),
            "avg_latency_ms": round(avg_ms, 2),
            "min_latency_ms": round(min_ms, 2),
            "max_latency_ms": round(max_ms, 2),
            "p50_ms": round(p50_ms, 2),
            "p90_ms": round(p90_ms, 2),
            "p95_ms": round(p95_ms, 2),
            "p99_ms": round(p99_ms, 2),
            "status_breakdown": self.status_codes
        }

        # Request AI Analysis in non-blocking worker thread
        ai_recommendation = await asyncio.to_thread(self._call_ai_benchmark_analysis, setting, report_summary)

        report = BenchmarkReport(
            name=self.name,
            mode=self.mode,
            target_summary=self.target_summary,
            concurrent_users=self.concurrent_users,
            duration_seconds=self.duration_seconds,
            total_operations=self.total_ops,
            success_operations=self.success_ops,
            failed_operations=self.failed_ops,
            ops_per_sec=round(ops_per_sec, 1),
            avg_latency_ms=round(avg_ms, 2),
            min_latency_ms=round(min_ms, 2),
            max_latency_ms=round(max_ms, 2),
            p50_ms=round(p50_ms, 2),
            p90_ms=round(p90_ms, 2),
            p95_ms=round(p95_ms, 2),
            p99_ms=round(p99_ms, 2),
            status_breakdown_json=json.dumps(self.status_codes),
            metrics_timeline_json=json.dumps(self.timeline),
            ai_recommendation=ai_recommendation
        )

        # Persist report using dedicated DB session to avoid detached/closed session issues
        from .database import SessionLocal
        save_db = SessionLocal()
        try:
            save_db.add(report)
            save_db.commit()
            save_db.refresh(report)
            self.last_completed_report_id = report.id
            print(f"[Benchmark] Finished report #{report.id}: {self.name} ({ops_per_sec:.1f} ops/s, p99={p99_ms:.1f}ms)")
        except Exception as ex:
            save_db.rollback()
            print(f"[Benchmark] Failed to save report: {ex}")
        finally:
            save_db.close()

    def _call_ai_benchmark_analysis(self, setting, r: dict) -> str:
        """Calls AI Model to analyze performance benchmark results with real infrastructure and config awareness."""
        if not setting:
            return "AI Settings not configured"

        provider  = getattr(setting, "ai_provider", "lmstudio") or "lmstudio"
        host_url  = getattr(setting, "ai_host_url", "") or ""
        model_name = getattr(setting, "ai_model_name", "") or ""

        if not host_url or not model_name:
            return "AI Provider ยังไม่ได้ตั้งค่า"

        api_url = f"{host_url.rstrip('/')}/chat/completions"
        is_ollama_native = (provider == "ollama" and "/v1" not in host_url and ":11434" in host_url)
        if is_ollama_native:
            api_url = f"{host_url.rstrip('/')}/api/chat"

        # 1. Parse Server Hardware Infrastructure Specs
        server_specs_json = getattr(setting, "server_specs_json", None)
        specs_list = []
        if server_specs_json:
            try:
                specs_list = json.loads(server_specs_json) if isinstance(server_specs_json, str) else server_specs_json
            except Exception:
                pass

        if specs_list and isinstance(specs_list, list):
            hw_lines = ["### ข้อมูลทรัพยากรฮาร์ดแวร์เซิร์ฟเวอร์จริง (Production Hardware Specifications):"]
            for idx, spec in enumerate(specs_list, 1):
                if not isinstance(spec, dict):
                    continue
                name = spec.get('name', f'Server-{idx}')
                role = spec.get('role', 'N/A')
                cpu = spec.get('cpu_model', '')
                cores = spec.get('cpu_cores', '')
                ram = spec.get('ram_gb', '')
                storage = spec.get('storage_type', '')
                sz = f" ({spec['storage_size_gb']} GB)" if spec.get('storage_size_gb') else ""
                notes = spec.get('notes', '')
                hw_lines.append(f"- **{name}** ({role}): CPU {cores} Cores ({cpu}), RAM {ram} GB, Storage {storage}{sz}" + (f" [{notes}]" if notes else ""))
            hw_context = "\n".join(hw_lines)
        else:
            hw_context = (
                "### ข้อมูลทรัพยากรฮาร์ดแวร์เซิร์ฟเวอร์จริง (Production Hardware Specifications Baseline):\n"
                "- **WMS-DB Server (10.1.1.9)**: 16 vCPUs (Intel Xeon Platinum 8168), RAM 64 GB, 500 GB NVMe SSD\n"
                "- **TMS-DB Server (10.1.1.24)**: 16 vCPUs (Intel Xeon Platinum 8168), RAM 32 GB, 350 GB NVMe SSD\n"
                "- **WMS-APP / Web Server (10.1.1.4)**: 16 vCPUs, RAM 32 GB (รัน 14 สาขาคอนเทนเนอร์)"
            )

        # 2. Parse Active Database & PgBouncer Configuration
        pg_conf = getattr(setting, "postgresql_conf", None) or ""
        pgb_ini = getattr(setting, "pgbouncer_ini", None) or ""

        cfg_lines = ["### สถานะการตั้งค่า Database และ Connection Pool ปัจจุบัน (Active Configurations):"]
        if pg_conf.strip():
            cfg_lines.append("#### คอนฟิก PostgreSQL ปัจจุบัน (postgresql.conf):")
            cfg_lines.append(f"```ini\n{pg_conf[:3000].strip()}\n```")
        else:
            cfg_lines.append(
                "- **PostgreSQL 16 Tuning (WMS-DB 10.1.1.9)**: `shared_buffers = 16GB` (25% ของ RAM 64GB), "
                "`effective_cache_size = 48GB` (75% ของ RAM), `work_mem = 32MB`, `maintenance_work_mem = 2GB`, `max_connections = 300`"
            )

        if pgb_ini.strip():
            cfg_lines.append("#### คอนฟิก PgBouncer ปัจจุบัน (pgbouncer.ini):")
            cfg_lines.append(f"```ini\n{pgb_ini[:3000].strip()}\n```")
        else:
            cfg_lines.append(
                "- **PgBouncer Status**: เปิดใช้งานและรันอยู่จริงบน Port 6432 (`pool_mode = transaction`, "
                "`default_pool_size = 30`, `min_pool_size = 10`, `reserve_pool_size = 15`, `max_client_conn = 1000`)"
            )
        config_context = "\n".join(cfg_lines)

        # 3. Format Target Detail
        target_detail = ""
        if r.get("mode") == "postgres":
            db_info = r.get("target_db_info") or {}
            host = db_info.get("host", "N/A")
            port = db_info.get("port", "N/A")
            dbname = db_info.get("dbname", "N/A")
            sql = r.get("target_sql") or r.get("target_summary")
            pool_note = ""
            if str(port) == "6432":
                pool_note = " ⚡ (การทดสอบนี้ยิงผ่าน PgBouncer Transaction Connection Pool โดยตรง)"
            elif str(port) == "5432":
                pool_note = " ⚠️ (การทดสอบนี้ยิงตรงเข้า PostgreSQL Native Engine Port 5432)"
            target_detail = (
                f"- **ฐานข้อมูลเป้าหมาย**: Host `{host}`, Port `{port}`, Database `{dbname}`{pool_note}\n"
                f"- **คำสั่ง SQL Statement ที่ทดสอบ**:\n```sql\n{sql}\n```"
            )
        else:
            url = r.get("target_url") or r.get("target_summary")
            method = r.get("target_method") or "HTTP"
            target_detail = f"- **HTTP Endpoint เป้าหมาย**: `{method}` `{url}`"

        system_prompt = (
            "คุณคือ Principal Database Administrator (DBA), Senior Performance Engineer และ System Architect ผู้เชี่ยวชาญระดับสูงด้านระบบ WMS/TMS\n"
            "หน้าที่ของคุณคือวิเคราะห์ผลการทดสอบประสิทธิภาพ (Performance Benchmark Load Test) "
            "อย่างแม่นยำ ตรงไปตรงมา อิงตามสภาพแวดล้อมฮาร์ดแวร์จริง (Real Infrastructure Specs) และคอนฟิกของระบบจริง (Active Production Config) ที่ให้ไว้อย่างเคร่งครัด\n\n"
            "======================================================================\n"
            "🚨 กฎเหล็กสำคัญอย่างยิ่ง (STRICT ARCHITECTURAL RULES):\n"
            "======================================================================\n"
            "1. [ห้ามแนะนำให้ติดตั้ง PgBouncer เด็ดขาด]:\n"
            "   - ระบบมี PgBouncer ติดตั้งและเปิดใช้งานอยู่แล้วบน Port 6432 (Transaction Pooling) ตามที่ระบุใน pgbouncer.ini\n"
            "   - หาก Port ที่ทดสอบคือ 6432 แปลว่ากำลังรันผ่าน PgBouncer อยู่แล้ว ห้ามพูดว่า 'หากยังไม่ได้ใช้ แนะนำให้ติดตั้ง PgBouncer' เด็ดขาด!\n\n"
            "2. [ห้ามแนะนำให้ปรับ shared_buffers เป็น 25% ของ RAM เด็ดขาด]:\n"
            "   - เซิร์ฟเวอร์ WMS-DB (10.1.1.9) มี RAM 64GB และได้ตั้งค่า `shared_buffers = 16GB` (คิดเป็น 25% ของ RAM) ไว้อย่างถูกต้องสมบูรณ์แล้วใน postgresql.conf\n"
            "   - ห้ามแนะนำให้ไปตรวจสอบหรือตั้งค่า 25% ซ้ำซ้อนอีก เพราะทำไปแล้วและทำงานอยู่จริงแล้ว!\n\n"
            "3. [ประเมิน Latency และ Throughput เทียบกับ Production Baseline จริงอย่างสมเหตุสมผล]:\n"
            "   - ภาระงานจริงของ WMS/TMS มีปริมาณ Transaction ปกติเพียง 10 - 20 QPS เท่านั้น\n"
            "   - หากผล Benchmark ทำได้ระดับ 1,000 - 3,000+ ops/sec ถือเป็นประสิทธิภาพที่รองรับโหลดได้สูงกว่าโหลดจริงในระบบถึง 100 - 200 เท่า (Very High Capacity)\n"
            "   - การทดสอบด้วย Simulated Users จำนวนมากแบบ Zero-Think-Time (ยิงต่อเนื่องวนลูปไม่มีหยุด) แล้วได้ Success Rate 100% ถือเป็นประสิทธิภาพระดับ 'ยอดเยี่ยมและเสถียรมาก' (Healthy & Rock-solid)\n"
            "   - ค่า p99 ที่ประมาณ 30-70 ms ภายใต้ Concurrency ระดับ 100-300 Users เกิดจาก Socket / Connection Queueing ตามธรรมชาติเมื่อหลายร้อย Worker แย่ง CPU Cores ไม่ใช่ปัญหา Jitter หรือ Bottleneck วิกฤต ห้ามตื่นตระหนกเกินจริง!\n\n"
            "4. [วิเคราะห์แยกแยะตามประเภทของ Target Query ให้ตรงจุด]:\n"
            "   - หาก Query เป็นการอ่านตารางระบบ / สถิติ (เช่น pg_stat_database, sum(blks_read), sum(xact_commit)):\n"
            "     * นี่คือสถิติระดับ Engine สำหรับงาน Dashboard / Monitoring ไม่ใช่ Query การทำงานจริงของธุรกิจ (Business Query)\n"
            "     * คำแนะนำที่ถูกต้อง: ให้แนะนำทำ Application Caching (Redis Cache TTL 5-15 วินาที) สำหรับหน้า Dashboard สถิติ หรือย้ายงานสถิติไปอ่านจาก Read Replica (10.1.1.99) เพื่อไม่ให้รบกวน Master DB\n"
            "   - หาก Query เป็น Business Query บนตาราง WMS/TMS (schema 'dc' หรือ 'public'):\n"
            "     * แนะนำให้ตรวจเช็ค Index บนคอลัมน์ใน WHERE/JOIN (พึงจำว่า schema WMS คือ 'dc' และชื่อคอลัมน์ผู้ใช้คือ 'user_name') และใช้ EXPLAIN (ANALYZE, BUFFERS)\n\n"
            "5. [คำแนะนำด้าน Application Connection Pool ที่ถูกต้อง]:\n"
            "   - แนะนำการปรับ Application Connection Pool (เช่น HikariCP ใน Spring Boot): ให้ตั้ง maximumPoolSize ให้สัมพันธ์กับ PgBouncer default_pool_size (เช่น 10-30 connections ต่อ App instance)\n\n"
            "6. [รูปแบบการตอบ]:\n"
            "   - ห้ามใช้แท็ก HTML ทุกชนิด (<br>, <b>, <span> ฯลฯ) Output ต้องเป็น Clean Markdown เท่านั้น"
        )

        success_pct = (r['success_operations'] / max(1, r['total_operations'])) * 100.0
        user_prompt = f"""รายงานผลการทดสอบประสิทธิภาพ (Performance Benchmark Load Test Result):

### 1. ข้อมูลการทดสอบ (Test Setup):
- **ชื่อการทดสอบ**: {r['name']}
- **โหมดการทดสอบ**: {r['mode'].upper()}
{target_detail}
- **จำนวน Concurrent Simulated Users**: {r['concurrent_users']} users (Zero-Think-Time Loop)
- **ระยะเวลาการทดสอบ**: {r['duration_seconds']} วินาที
- **จำนวน Operations ทั้งหมด**: {r['total_operations']:,} รายการ
- **อัตราความสำเร็จ (Success Rate)**: {r['success_operations']:,} / {r['total_operations']:,} ({success_pct:.2f}%)
- **จำนวนความล้มเหลว (Failed / Errors)**: {r['failed_operations']} รายการ
- **Throughput อัตราการประมวลผล**: **{r['ops_per_sec']:,} ops/sec** (เทียบกับ Production Normal Peak ที่ 10-20 QPS)

### 2. ข้อมูล Latency Profile (มิลลิวินาที):
- **Average Latency**: {r['avg_latency_ms']} ms
- **Min Latency**: {r.get('min_latency_ms', 0)} ms
- **Max Latency**: {r.get('max_latency_ms', 0)} ms
- **p50 (Median)**: {r['p50_ms']} ms
- **p90**: {r['p90_ms']} ms
- **p95**: {r['p95_ms']} ms
- **p99 (Worst 1% Tail Latency)**: {r['p99_ms']} ms
- **Status Codes Breakdown**: {json.dumps(r['status_breakdown'], ensure_ascii=False)}

---
{hw_context}
---
{config_context}
---

จงวิเคราะห์ผลการทดสอบและตอบตามโครงสร้างต่อไปนี้อย่างละเอียด ชัดเจน และเป็นมืออาชีพ:

## 1. 📊 Performance Summary & Capacity Assessment
(ประเมินสถานะระบบ โดยเทียบ Throughput และ Latency กับปริมาณโหลดจริงของระบบ WMS/TMS ซึ่งปกติอยู่ที่ 10-20 QPS พร้อมประเมินความเสถียรและ Success Rate ภายใต้ Concurrency {r['concurrent_users']} Users)

## 2. 🔍 Realistic Latency & Concurrency Analysis
(วิเคราะห์ค่า p50/p90/p99 ภายใต้ Concurrent Users {r['concurrent_users']} คน อธิบายสาเหตุของค่า p99 อย่างสมเหตุสมผลตามสภาพแวดล้อมฮาร์ดแวร์จริง เช่น Socket queueing / PgBouncer pool queueing โดยไม่ตื่นตระหนกเกินจริง)

## 3. 🎯 Targeted & Actionable Recommendations
(ให้คำแนะนำที่ตรงจุด ปฏิบัติได้จริง สอดคล้องกับสภาพแวดล้อมที่ตั้งค่าไว้แล้ว โดยยึดตามกฎเหล็ก ห้ามแนะนำสิ่งที่ระบบทำไว้แล้ว เช่น PgBouncer หรือ shared_buffers 25% แต่ให้แนะนำด้าน Application Caching (Redis), Read Replica, HikariCP Sizing, หรือ Indexing ที่เหมาะสมกับชนิดของ Query)"""

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
                if choices:
                    return choices[0].get("message", {}).get("content", "No content from AI")
            return f"AI API Error: {resp.status_code}"
        except Exception as e:
            return f"ไม่สามารถเชื่อมต่อ AI เพื่อวิเคราะห์ผล: {type(e).__name__}"


# Global Singleton Instance
benchmark_engine = BenchmarkEngine()
