# AI Log Analyzer - Modern DevOps Assistant (WMS & TMS)

ระบบเว็บแอปพลิเคชันสำหรับเฝ้าระวัง วิเคราะห์ปัญหาประสิทธิภาพ (High Latency) และจับคู่ประมวลผลข้อผิดพลาด (Error Logs) จากระบบ WMS และ TMS บน Production โดยนำข้อมูลประสานงานจาก Grafana Loki และ Percona Monitoring and Management (PMM) ส่งให้ Local AI (LM Studio, Ollama, Hermes) สรุปวิเคราะห์คอขวดเชิงลึก

---

## 🛠️ Tech Stack & Architecture

- **Frontend**: React + Vite (Vanilla CSS Premium Glassmorphism UI)
- **Backend API**: Python FastAPI (Uvicorn)
- **Caching & Scheduler Lock**: Redis (ป้องการรันงานซ้ำบน K8s)
- **Database**: PostgreSQL (เก็บประวัติการรันและค่าคอนฟิก)
- **Object Storage**: Minio (สำหรับเก็บ Backup/Archive รายงานสรุปแบบดิบ)
- **Gateway/Proxy**: Nginx (จัดการ Routing หน้าบ้านและหลังบ้าน)

---

## 🚀 วิธีการรันในเครื่องส่วนตัว (Docker Compose)

ในไดเรกทอรีหลักของโปรเจกต์ สั่งรันทุกบริการด้วยคำสั่งเดียว:

```bash
docker compose up --build -d
```

### รายละเอียดการเข้าใช้งาน:
- **Web Application Dashboard**: [http://localhost](http://localhost) (Nginx port 80)
  - *Default Login*: Username: `admin` | Password: `admin` (สามารถเปลี่ยนรหัสผ่านได้ในหน้า Settings)
- **Minio Console (Object Storage)**: [http://localhost:9001](http://localhost:9001)
  - *Default login*: admin/admin: `minioadmin` | `minioadmin`

---

## 💡 วิธีการเชื่อมต่อกับ AI Model ในเครื่อง Host (Localhost)

เนื่องจากโมเดล AI (LM Studio / Ollama) ของคุณรันอยู่บนเครื่องคอมพิวเตอร์หลัก (Host) และเราต้องการให้ API ที่ทำงานอยู่ใน Container วิ่งเข้าไปคุยได้:

1. ล็อกอินเข้าเว็บหน้าบ้าน -> ไปที่เมนู **Settings**
2. ในการตั้งค่า **AI API Host URL** ให้ใช้ IP กลางที่ชี้กลับมาที่เครื่องหลัก:
   - **LM Studio**: `http://host.docker.internal:1234/v1`
   - **Ollama**: `http://host.docker.internal:11434`
3. สคริปต์หลังบ้านได้รับการกำหนดค่า `extra_hosts` ใน `docker-compose.yml` ให้แปลง `host.docker.internal` วิ่งเข้าประตู Host Gateway เรียบร้อยแล้ว

---

## ☸️ แนวทางการติดตั้งไปยัง Kubernetes (Talos OS + Rook-Ceph)

ตัวไฟล์ Manifest สำหรับ Kubernetes ได้รับการจัดเตรียมไว้ที่ [k8s/app-deployment.yaml](file:///c:/Users/arthit.n/git/ai_analyzer/k8s/app-deployment.yaml) ซึ่งออกแบบมาเฉพาะสำหรับ **Rook-Ceph storage class** และระบบ Cluster บน **Talos OS**:

### 1. Build and Push Docker Images
ก่อนทำการติดตั้ง ให้ทำการ Build และ Push Docker Image ของ Backend และ Frontend ไปยัง Private Docker Registry ของคุณ:

```bash
# Build & Push Backend
docker build -t your-docker-registry/ai-analyzer-backend:latest ./backend
docker push your-docker-registry/ai-analyzer-backend:latest

# Build & Push Frontend
docker build -t your-docker-registry/ai-analyzer-frontend:latest ./frontend
docker push your-docker-registry/ai-analyzer-frontend:latest
```
*(แก้ไขชื่อ Image ในไฟล์ [k8s/app-deployment.yaml](file:///c:/Users/arthit.n/git/ai_analyzer/k8s/app-deployment.yaml) ที่บรรทัด backend และ frontend ให้ถูกต้อง)*

### 2. Apply Manifests
สั่งติดตั้งทรัพยากรทั้งหมดขึ้น Kubernetes Cluster:

```bash
kubectl apply -f k8s/app-deployment.yaml
```

### 3. รายละเอียดการตั้งค่า K8s:
- **Persistent Volume Claim (PVC)**: ระบบจะส่งคำขอสร้าง Block Storage ขนาด 10GB (Postgres) และ 20GB (Minio) ไปยัง Rook-Ceph ด้วย Storage Class `storageClassName: rook-ceph-block` อัตโนมัติ
- **Ingress Controller**: ใช้ Nginx Ingress Controller ในการจัดการ Routing ไปยัง Frontend และ Backend
  - โดเมนเริ่มต้น: `ai-analyzer.local` (สามารถแก้ไขค่า host ใน Ingress section ได้)
- **High Availability**: ตัว backend และ frontend ทำการเซ็ตอัป `replicas: 2` และระบบหลังบ้านจะคอยเช็คสิทธิ์การรันวิเคราะห์ซ้ำซ้อนผ่านตัวล็อก Redis Lock ใน Redis Service เสมอ ทำให้ไม่เกะกะการทำงานร่วมกันบน Cluster
