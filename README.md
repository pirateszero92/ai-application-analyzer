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

## 🛠️ รายงานสรุปการปรับจูนประสิทธิภาพฐานข้อมูล WMS & TMS (Production Tuning & Case Study)

บันทึกสรุปการแก้ไขปัญหาคอขวดและปรับจูนประสิทธิภาพของระบบฐานข้อมูล **WMS Production (`10.1.1.9`)**, **TMS Production (`10.1.1.24`)**, และการดูแลคลีนอัพเครื่อง **WMS UAT Clone (`10.1.1.195`)**

---

### 1. 📊 สรุปปัญหาที่ตรวจพบก่อนการจูน (Identified Bottlenecks)

| หัวข้อปัญหา | รายละเอียดที่ตรวจพบในระบบเดิม | ผลกระทบต่อระบบ |
| :--- | :--- | :--- |
| **High Idle Connections** | พบ Active/Idle Connection ค้างใน PostgreSQL สูงถึง 145+ เชื่อมต่อ (Idle ค้าง 50+ คอนเนกชัน) ทั้งที่ QPS มีเพียง 9 - 15 ops/s | เปลือง RAM Server โดยเปล่าประโยชน์ (~400MB+) และเสี่ยงชนเพดาน `max_connections` |
| **PMM Monitoring Overhead** | คิวรี `SELECT pg_database_size(...)` ของ PMM Agent รันถี่ทุก 30 วินาที สะสมกว่า 11.75 ล้านครั้ง (เวลารวมกว่า 49.3 ชั่วโมง) | เกิด Disk I/O Spikes และ Filesystem Contention จากการไล่ `stat()` ไฟล์ Tablespace บ่อยเกินจำเป็น |
| **Seq Scan บน Small Tables** | ตาราง Config/Master ขนาดเล็ก เช่น `dc.wms_users`, `dc.wms_menu` มีอัตรา Sequential Scan สูง 98-99% | ทีมกังวลเรื่องประสิทธิภาพและการขาด Index |
| **WAL Disk Bloat บน UAT Clone** | เซิร์ฟเวอร์ `db-wms-uat` (`10.1.1.195`) ที่โคลนมาจาก Production มี Replication Slot ค้าง ดัก WAL ไฟล์ไว้กว่า 7.0 GB | พื้นที่ดิสก์เต็ม เสี่ยงต่อการล่มของระบบฐานข้อมูล |

---

### 2. ⚡ การปรับแต่ง Connection Pool (PgBouncer Tuning)

#### 🔍 สาเหตุ (Root Cause):
ในไฟล์ `/etc/pgbouncer/pgbouncer.ini` ค่า `min_pool_size` ถูกตั้งไว้สูงเกินจริง (WMS = 50, TMS = 20) ทำให้ PgBouncer บังคับเปิด Connection แช่ค้างไว้กับ PostgreSQL ตลอดเวลา แม้ช่วงที่ไม่มีโหลดผู้ใช้งาน

#### ⚙️ การแก้ไขคอนฟิก (`/etc/pgbouncer/pgbouncer.ini`):
- **WMS-DB (`10.1.1.9`)**:
  ```ini
  default_pool_size = 30    ; เดิม 300 (ลดลงให้สมดุลกับ 10-15 QPS)
  min_pool_size = 10        ; เดิม 50  (ลด idle worker ที่เปิดค้าง)
  reserve_pool_size = 15    ; เดิม 150 (สำรองเมื่อเกิด traffic burst)
  ```
- **TMS-DB (`10.1.1.24`)**:
  ```ini
  default_pool_size = 30    ; เดิม 200
  min_pool_size = 5         ; เดิม 20
  reserve_pool_size = 15    ; เดิม 100
  ```

#### 🔄 คำสั่ง Reload (Zero Downtime):
```bash
sudo systemctl reload pgbouncer
```

#### 📈 ผลลัพธ์หลังการปรับปรุง:
- **WMS Production**: Idle Connections ลดลงจาก **51 ➔ เหลือเพียง 11 คอนเนกชัน** (ลดลงถึง 78.4%) ประหยัดหน่วยความจำ Server ไปทันทีกว่า 400 MB
- **TMS Production**: Idle Connections ลดลงจาก **31 ➔ เหลือเพียง 16 คอนเนกชัน** (ลดลง 48.3%)

---

### 3. 📉 ลดภาระคิวรีมอนิเตอร์ PMM Agent (`pg_database_size`)

#### 🔍 สาเหตุ (Root Cause):
PMM Agent มี Custom Query สำหรับ Medium Resolution (`queries-mr.yaml`) ที่เรียกฟังก์ชัน `pg_database_size()` บ่อยทุกๆ 30 วินาที ซึ่งฟังก์ชันนี้จะสแกนและเรียก OS System Call (`stat()`) ข้ามทุกไฟล์บนดิสก์ ส่งผลให้เกิด I/O Overhead สูงอย่างต่อเนื่อง

#### ⚙️ การแก้ไขคอนฟิก PMM Agent:
ไฟล์: `/usr/local/percona/pmm/collectors/custom-queries/postgresql/medium-resolution/queries-mr.yaml`
```yaml
# ปรับแคชความถี่จากเดิม 30 วินาที เป็น 600 วินาที (10 นาที)
pg_database:
  query: "SELECT pg_database.datname, pg_database_size(pg_database.datname) as size_bytes FROM pg_database"
  metrics:
    - datname:
        usage: "LABEL"
        description: "Name of the database"
    - size_bytes:
        usage: "GAUGE"
        description: "Disk space used by the database"
  cache_seconds: 600    # เดิม: 30
```

#### 🔄 คำสั่งรีสตาร์ทเอเจนต์:
```bash
sudo systemctl restart pmm-agent
```

#### 📈 ผลลัพธ์:
- ลดภาระ Disk I/O และ Catalog Scan บน Production ลงได้มากกว่า **95%**
- กราฟขนาดฐานข้อมูลบน PMM Dashboard ยังคงอัปเดตแม่นยำทุก 10 นาทีโดยไม่มีผลเสียต่อการเฝ้าระวัง

---

### 4. 🧠 การวิเคราะห์ตารางขนาดเล็กและ Sequential Scan

#### 🔍 ข้อเท็จจริงทางเทคนิค (PostgreSQL Planner Optimization):
จากการตรวจสอบตาราง `dc.wms_users` (1,234 rows), `dc.wms_menu` (34 rows), และ `dc.wms_rolexmenu` (52 rows):
- ขนาดตารางเหล่านี้มีขนาดเล็กมาก (ใช้พื้นที่เพียง 1-8 Disk Pages หรือ < 64KB)
- PostgreSQL Cost-based Optimizer จงใจเลือก **Sequential Scan** แทน Index Scan เนื่องจาก:
  1. การอ่านทั้งตารางขึ้น Shared Buffers ใช้ disk page read เพียง 1 ครั้ง
  2. การทำ Index Scan ต้องอ่าน B-Tree Root ➔ Branch ➔ Leaf ➔ Heap Page ซึ่งกิน CPU cycle และ buffer lookup มากกว่า
- **สรุป**: เป็นพฤติกรรมปกติที่ถูกต้องและมีประสิทธิภาพสูงสุดอยู่แล้ว (Latency < 0.8ms)

#### 🛠️ การบำรุงรักษาสถิติ (Statistics Update):
ได้ทำการรัน `ANALYZE` ตารางดังกล่าวเพื่อให้ Query Planner มีค่าสถิติการกระจายตัวของข้อมูลล่าสุด:
```sql
-- WMS Production
ANALYZE dc.wms_users;
ANALYZE dc.wms_menu;
ANALYZE dc.wms_rolexmenu;

-- TMS Production
ANALYZE public.tms_notification_outbox;
ANALYZE public.tms_employees;
ANALYZE public.tms_users;
ANALYZE public.tms_menu;
ANALYZE public.tms_rolexmenu;
```

---

### 5. 🧹 การปลด Replication บนเครื่อง UAT Clone (`10.1.1.195`) และคืนพื้นที่ Disk

เมื่อทำการ Clone เครื่อง Production มาเป็น UAT ระบบเดิมจะมี Replication Slot และสิทธิ์การต่อเชื่อมค้างอยู่ ซึ่งตัว Slot จะกักเก็บไฟล์ Write-Ahead Log (WAL) ไม่ยอมให้ลบ จนกว่า Replica จะมารับข้อมูล ส่งผลให้พื้นที่ดิสก์เต็ม

#### ขั้นตอนที่ดำเนินการ:
1. **ตรวจสอบ Slot ที่ค้างและขนาด WAL ที่ถูกดักไว้**:
   ```sql
   SELECT slot_name, plugin, active,
          pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal_bytes
   FROM pg_replication_slots;
   ```
2. **ลบ Inactive Replication Slot**:
   ```sql
   SELECT pg_drop_replication_slot('replica_1');
   ```
3. **บังคับ Checkpoint เพื่อ Purge ลบไฟล์ WAL ส่วนเกินคืนพื้นที่ดิสก์**:
   ```sql
   CHECKPOINT;
   ```
   *(สามารถกู้คืนพื้นที่ดิสก์กลับมาได้ทันที 7.0 GB)*
4. **ปิดสิทธิ์ Replication User ใน `pg_hba.conf`**:
   แก้ไขไฟล์ `/etc/postgresql/16/main/pg_hba.conf` โดยใส่เครื่องหมาย `#` ปิดบรรทัด `replica_user` จากนั้นสั่ง reload:
   ```bash
   sudo systemctl reload postgresql
   ```

---

### 6. 🚨 Emergency Runbook: ขั้นตอนการ Promote Standby Replica เป็น Primary เมื่อ Master ล่ม

ในกรณีที่เครื่อง Master (Primary) เกิดความเสียหายร้ายแรงจนไม่สามารถกู้คืนได้ และจำเป็นต้องสลับ Replica ขึ้นมาเป็น Primary ให้ดำเนินการตามขั้นตอนดังนี้:

#### ขั้นตอนที่ 1: ตรวจสอบสถานะ Standby Server
ล็อกอินเข้าเครื่อง Replica แล้วเปิด `psql` ตรวจสอบสถานะการ Recovery:
```sql
-- ต้องได้ผลลัพธ์เป็น true (แสดงว่าเครื่องนี้เป็น Standby)
SELECT pg_is_in_recovery();

-- ตรวจสอบ LSN ล่าสุดที่ Replicate มาว่าตามหลัง Primary มากน้อยเพียงใด
SELECT pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn(),
       pg_last_xact_replay_timestamp();
```

#### ขั้นตอนที่ 2: ดำเนินการ Promote Replica ขึ้นเป็น Primary
สามารถเลือกทำได้ 1 วิธีจาก 2 วิธีด้านล่าง:

- **วิธีที่ A (รันผ่าน SQL บน psql)**:
  ```sql
  SELECT pg_promote();
  ```
- **วิธีที่ B (รันผ่าน OS Terminal)**:
  ```bash
  # สำหรับ PostgreSQL 16 (Ubuntu/Debian)
  sudo -u postgres /usr/lib/postgresql/16/bin/pg_ctl promote -D /var/lib/postgresql/16/main
  ```

#### ขั้นตอนที่ 3: ตรวจสอบยืนยันว่ากลายเป็น Primary เรียบร้อยแล้ว
```sql
-- ต้องได้ผลลัพธ์เป็น false (พร้อมรับ Read/Write เต็มรูปแบบ)
SELECT pg_is_in_recovery();
```

#### ขั้นตอนที่ 4: สลับการชี้ของ Application / PgBouncer
1. อัปเดตปลายทาง IP ใน PgBouncer (`/etc/pgbouncer/pgbouncer.ini`) ให้ชี้มายัง IP ของเครื่องใหม่ที่เพิ่งถูก Promote:
   ```ini
   [databases]
   wms = host=<NEW_PRIMARY_IP> port=5432 dbname=wms
   ```
2. Reload PgBouncer:
   ```bash
   sudo systemctl reload pgbouncer
   ```
3. ตรวจสอบ Log ของ Application Backend เพื่อยืนยันว่า Transaction Write ทำงานได้ปกติ

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
