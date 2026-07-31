import asyncio
import time
import json
import math
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
import psycopg2

class BenchmarkEngine:
    """
    Asynchronous Benchmark Engine for HTTP APIs and Direct PostgreSQL Queries.
    Calculates real-time RPS/QPS, latency percentiles (p50/p90/p95/p99),
    and requests AI Performance Optimization Analysis upon test completion.
    """
    def __init__(self):
        self.is_running = False
        self.should_stop = False
        self.name = "Benchmark Run"
        self.mode = "http"  # 'http' or 'postgres'
        self.target_summary = ""
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
        self.concurrent_users = max(1, min(500, concurrent_users))
        self.duration_seconds = max(3, min(300, duration_seconds))
        self.start_time = time.time()

        self.total_ops = 0
        self.success_ops = 0
        self.failed_ops = 0
        self.latencies_ms = []
        self.status_codes = {}
        self.timeline = []
        self.last_error = None

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

        # Background monitor task for timeline sampling
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

        self.is_running = False
        self.elapsed_seconds = time.time() - self.start_time
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
        self.concurrent_users = max(1, min(200, concurrent_users))
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
                cur = conn.cursor()

                while time.time() < end_time and not self.should_stop:
                    t0 = time.perf_counter()
                    try:
                        cur.execute(sql_query)
                        cur.fetchall()  # fetch result if any
                        lat = (time.perf_counter() - t0) * 1000.0

                        self.total_ops += 1
                        self.success_ops += 1
                        self.latencies_ms.append(lat)
                        self.status_codes["OK"] = self.status_codes.get("OK", 0) + 1
                    except Exception as e:
                        conn.rollback()
                        lat = (time.perf_counter() - t0) * 1000.0
                        self.total_ops += 1
                        self.failed_ops += 1
                        err_name = type(e).__name__
                        self.status_codes[err_name] = self.status_codes.get(err_name, 0) + 1
                        self.latencies_ms.append(lat)
                    time.sleep(0.001)
                conn.close()
            except Exception as e:
                self.last_error = f"Connection error: {e}"

        # Run DB workers in ThreadPool
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=self.concurrent_users) as executor:
            sampler_task = asyncio.create_task(self._async_sampler())
            futures = [loop.run_in_executor(executor, _db_worker_func) for _ in range(self.concurrent_users)]
            await asyncio.gather(*futures)

        self.is_running = False
        self.elapsed_seconds = time.time() - self.start_time

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
            "concurrent_users": self.concurrent_users,
            "duration_seconds": self.duration_seconds,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "total_operations": self.total_ops,
            "success_operations": self.success_ops,
            "failed_operations": self.failed_ops,
            "ops_per_sec": round(ops_per_sec, 1),
            "avg_latency_ms": round(avg_ms, 2),
            "p50_ms": round(p50_ms, 2),
            "p90_ms": round(p90_ms, 2),
            "p95_ms": round(p95_ms, 2),
            "p99_ms": round(p99_ms, 2),
            "status_breakdown": self.status_codes
        }

        # Request AI Analysis
        ai_recommendation = self._call_ai_benchmark_analysis(setting, report_summary)

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

        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        self.last_completed_report_id = report.id
        print(f"[Benchmark] Finished report #{report.id}: {self.name} ({ops_per_sec:.1f} ops/s, p99={p99_ms:.1f}ms)")

    def _call_ai_benchmark_analysis(self, setting, r: dict) -> str:
        """Calls AI Model to analyze performance benchmark results."""
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

        system_prompt = (
            "คุณคือ Senior Performance Engineer & System Architect ผู้เชี่ยวชาญด้านระบบ WMS/TMS "
            "หน้าที่ของคุณคือวิเคราะห์ผลการรันทดสอบประสิทธิภาพ (Performance Benchmark Load Test) "
            "ประเมินคอขวด (Bottlenecks), ค่า Latency Percentiles (p50/p90/p99), อัตรา QPS/RPS และให้คำแนะนำการเพิ่มประสิทธิภาพจูนระบบ\n\n"
            "กฎเหล็ก: ห้ามใช้ HTML แท็กทุกชนิด (<br>, <b> ฯลฯ) Output ต้องเป็น Pure Markdown เท่านั้น"
        )

        user_prompt = f"""ผลการทดสอบประสิทธิภาพ (Performance Benchmark Load Test):

- **ชื่อการทดสอบ**: {r['name']}
- **โหมด**: {r['mode'].upper()} (Target: {r['target_summary']})
- **จำลอง User เข้าพร้อมกัน (Simulated Users)**: {r['concurrent_users']} users
- **ระยะเวลาการทดสอบ**: {r['duration_seconds']} วินาที
- **จำนวน Operations ทั้งหมด**: {r['total_operations']} รายการ (สำเร็จ: {r['success_operations']}, ล้มเหลว/Error: {r['failed_operations']})
- **Throughput (RPS/QPS)**: {r['ops_per_sec']} ops/sec
- **Average Latency**: {r['avg_latency_ms']} ms
- **Percentiles**:
  - p50 (Median): {r['p50_ms']} ms
  - p90: {r['p90_ms']} ms
  - p95: {r['p95_ms']} ms
  - p99 (Worst 1%): {r['p99_ms']} ms
- **Status Breakdown**: {json.dumps(r['status_breakdown'])}

---

จงวิเคราะห์และตอบตามโครงสร้างต่อไปนี้:

## Performance Summary & Health Assessment
(ประเมินประสิทธิภาพโดยรวมภายใต้จำนวน {r['concurrent_users']} Concurrent Users)

## Latency & Bottleneck Analysis
(วิเคราะห์ค่า p90/p99, สาเหตุของความช้า และคอขวดที่อาจเกิดขึ้น)

## AI Optimization & Tuning Recommendations
(คำแนะนำการจูนระบบ ทั้งด้าน Database Index, Connection Pool, JVM Heap, หรือ API Rate Limit)"""

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
