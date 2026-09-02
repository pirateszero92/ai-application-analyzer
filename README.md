# AI Log & Database Analyzer - Modern DevOps & DBA Assistant 🚀

ระบบเว็บแอปพลิเคชันอัจฉริยะสำหรับเฝ้าระวัง วิเคราะห์ปัญหาประสิทธิภาพ (High Latency, Slow Query, Disk I/O) และจับคู่ประมวลผลข้อผิดพลาด (Error Logs & Lock Contention) จากระบบ **WMS, TMS, และ Enterprise Applications** โดยนำข้อมูลประสานงานจาก **PostgreSQL Direct Telemetry, PgBouncer, Spring Boot Actuator, Grafana Loki, และ Prometheus** ส่งให้ **Local AI (LM Studio, Ollama, OpenAI-compatible)** สรุปวิเคราะห์ Root Cause และให้คำแนะนำแก้ไขปัญหาเชิงลึกแบบ Real-time

---

## 🌟 ฟีเจอร์หลักของระบบ (Key Features)

### 1. ⚡ Real-time PostgreSQL Observability & Lock Troubleshooter
- **Server-Sent Events (SSE)**: สตรีมข้อมูลสดสถานะ Database Cluster ทุก 2 วินาทีโดยไม่ต้อง Refresh
- **🔴 Visual Lock Tree & Blocker Graph**: แสดงแผนผังความสัมพันธ์คิวรีที่ติด Lock ตาราง (จับคู่ Session ตัวที่กัก Lock ต้นเหตุ ➔ กับ Session ที่ค้างรอ)
- **⚡ Emergency Remediation Actions**:
  - `🛑 Kill Blocker`: สั่งตัด Session ตัวที่ Lock ค้าง (`pg_terminate_backend`) ด้วยปุ่มเดียว
  - `⚠️ Cancel Query`: สั่งยกเลิกคำสั่ง SQL โดยไม่ตัด Connection (`pg_cancel_backend`)
  - `🤖 AI Troubleshoot Lock`: สั่ง AI วิเคราะห์ Root Cause และสร้างคำสั่งแก้ไขด่วนใน 1 นาที
- **⏱️ Active & Slow Queries Streaming**: ตรวจสอบคำสั่ง SQL ที่กำลังรันสดๆ ณ วินาทีนั้น พร้อม Duration, State, และ Wait Event
- **📊 Wait Events & Disk I/O Breakdown**: แจกแจงประเภทการรอคอยของ Database Engine (CPU, Lock, Disk I/O: DataFileRead/Write)
- **🔌 Connection Pools & Queues**: มอนิเตอร์คิวรอสายของ PgBouncer (Port 6432) และ Spring Boot HikariCP Pool

### 2. 🛡️ Proactive Health Monitoring & 24/7 Anomaly Detection
- คำนวณ **Health Score (0-100)** ตลอด 24 ชม. ตรวจจับความผิดปกติก่อนที่ระบบจะล่ม
- วิเคราะห์ความสัมพันธ์ข้ามระบบ (Container CPU/RAM, HikariCP Pending Queue, JVM Heap & GC Pause, Loki 5xx Error Rate)
- **Automated AI Root Cause Diagnosis**: วิเคราะห์สาเหตุอัตโนมัติตามกรอบ 4 ขั้นตอน (Root Cause Analysis, Immediate Actions, Root Cause Fix, Long-term Prevention)
- **Discord Alert Integration**: แจ้งเตือนสถานะความรุนแรง (CRITICAL / WARNING) พร้อมสรุปแนวทางแก้ไขเข้า Discord ทันที

### 3. 💬 Interactive AI Chat Assistant (Senior DevOps & DBA)
- บอทสนทนาอัจฉริยะที่ได้รับการผูกกับ **Live Database Probing Engine** ดึงข้อมูล Telemetry ของโหนดจริงมาวิเคราะห์ล่วงหน้าก่อนตอบคำถาม
- รองรับคำถามด้าน Database Performance Tuning, Index Optimization, PgBouncer Configuration, และ Spring Boot Connection Pool

### 4. 🧪 Benchmark Load & Stress Test Suite
- เครื่องมือทดสอบโหลดทั้ง **HTTP Endpoint** และ **PostgreSQL Direct Queries**
- จำลองผู้ใช้งานพร้อมกัน (Concurrent Users) และกำหนดระยะเวลาทดสอบ
- แสดงผล Real-time Throughput (QPS / RPS), ละเอียดระดับ Percentile Latency (Avg, Min, Max, p50, p90, p95, p99)
- AI Performance Optimization Report สรุปคอขวดและแนวทางขยายระบบหลังจบการทดสอบ

### 5. 📅 Daily Executive Summaries
- สรุปภาพรวมและสถิติ Incident ประจำวันอัตโนมัติ เพื่อให้ทีม DevOps และผู้บริหารติดตามแนวโน้มความเสถียรของระบบ

---

## 🛠️ Tech Stack & Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        React + Vite Frontend                            │
│           (Vanilla CSS Premium Glassmorphism UI + SSE Streaming)        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (HTTP / SSE / REST)
┌────────────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Backend Engine (Python 3.11)                 │
│  - Proactive Health Monitor Loop         - Real-time DB Lock Analyzer   │
│  - Live Telemetry & SQL Prober           - Benchmark Engine (HTTP/SQL)  │
│  - Multi-LLM Gateway (LM Studio/Ollama)  - Discord Webhook Notifier     │
└──────┬──────────────────────┬──────────────────────┬──────────────┬─────┘
       │                      │                      │              │
┌──────▼──────┐        ┌──────▼──────┐        ┌──────▼──────┐ ┌─────▼─────┐
│ PostgreSQL  │        │    Redis    │        │    MinIO    │ │Prometheus │
│  Metadata   │        │ Caching &   │        │   Reports   │ │ & Grafana │
│  & Reports  │        │ Job Locking │        │   Archive   │ │   Loki    │
└─────────────┘        └─────────────┘        └─────────────┘ └───────────┘
```

- **Frontend**: React 18 + Vite (Vanilla CSS Glassmorphism, Lucide Icons, EventSource SSE)
- **Backend API**: Python FastAPI (Uvicorn, Asyncio, Psycopg2, SQLAlchemy)
- **Caching & Locks**: Redis 7 (ป้องการรันงานชนกันในระบบ Distributed)
- **System Storage**: PostgreSQL 15 (Metadata, History, Health Events, Benchmarks)
- **Object Storage**: MinIO S3-Compatible (Raw Log Archive & Diagnostic Reports)
- **Reverse Proxy**: Nginx 1.25 Alpine

---

## 🚀 วิธีการรันบนเครื่อง Local / Server (Docker Compose)

ในโฟลเดอร์หลักของโปรเจกต์ รันทุก Service ด้วยคำสั่ง:

```bash
docker compose up -d --build
```

### การเข้าใช้งานระบบ:
- **Web Application Dashboard**: [http://localhost](http://localhost) (Port 80)
  - *Default Account*: Username: `admin` | Password: `admin` (สามารถเปลี่ยนรหัสผ่านได้ในหน้า Settings)
- **MinIO Console**: [http://localhost:9001](http://localhost:9001)
  - *Default Account*: `minioadmin` | `minioadmin`

---

## 💡 การเชื่อมต่อกับ Local AI (LM Studio / Ollama)

หากรันโมเดล AI บนเครื่องคอมพิวเตอร์หลัก (Host) และต้องการให้ Container หลังบ้านเชื่อมต่อเข้ามา:

1. เข้าหน้าเว็บ -> เมนู **Settings**
2. เลือก **AI Provider** และกรอก **AI Host URL**:
   - **LM Studio**: `http://host.docker.internal:1234/v1`
   - **Ollama**: `http://host.docker.internal:11434`
   - **OpenAI Compatible**: `https://api.openai.com/v1` (หรือ Custom Gateway)
3. ระบุ **Model Name** (เช่น `google/gemma-4-e4b`, `qwen2.5-coder`, `mistral`) แล้วกด **Save Settings**

---

## 🐘 การตั้งค่าการมอนิเตอร์ฐานข้อมูล PostgreSQL หลายโหนด

ในหน้า **Settings** -> ส่วน **Database Connections Configuration**:
ท่านสามารถเพิ่มรายการ Database Connection ได้ไม่จำกัด (เช่น `WMS-PROD`, `TMS-PROD`, `SPP-PROD`):
```json
[
  {
    "label": "WMS-PRODUCTION-DB",
    "host": "10.1.1.24",
    "port": 5432,
    "dbname": "wms",
    "user": "wms_user",
    "password": "your_password"
  },
  {
    "label": "TMS-PRODUCTION-DB",
    "host": "10.1.1.24",
    "port": 5432,
    "dbname": "tms",
    "user": "tms_user",
    "password": "your_password"
  }
]
```
ระบบจะทำการ Auto-probe เชื่อมต่อ, ตรวจสอบ Lock Tree, คิวรีที่รันนาน, และ Wait Events แบบ Real-time ทันที

---

## ☸️ แนวทางการติดตั้งไปยัง Kubernetes (Talos OS + Rook-Ceph)

ไฟล์ Manifest สำหรับ Kubernetes จัดเตรียมไว้ที่ `k8s/app-deployment.yaml` รองรับ **Rook-Ceph Block Storage** และ Cluster บน **Talos OS**:

### 1. Build and Push Docker Images
```bash
docker build -t your-registry/ai-analyzer-backend:latest ./backend
docker push your-registry/ai-analyzer-backend:latest

docker build -t your-registry/ai-analyzer-frontend:latest ./frontend
docker push your-registry/ai-analyzer-frontend:latest
```

### 2. Apply Kubernetes Manifests
```bash
kubectl apply -f k8s/app-deployment.yaml
```

---

## 📄 License
MIT License - Developed for Modern Cloud-Native Enterprise DevOps & DBA Observability.
