import requests
import json
import time
import urllib3
import sys
from datetime import datetime, timedelta

# Configure stdout/stderr to use UTF-8 encoding on Windows to prevent UnicodeEncodeError
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Disable SSL warnings for self-signed certificates (PMM)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- [ 1. การตั้งค่าระบบ (Configuration) ] ---
# IP Server Monitoring ตามที่คุณระบุไว้
LOKI_IP = "10.1.1.152"
LOKI_URL = f"http://{LOKI_IP}:3100/loki/api/v1/query_range"
LOKI_PROJECTS = ["wms", "tms"]

# PMM (Percona Monitoring and Management) Configuration
PMM_IP = "10.1.1.152"
PMM_PORT = "8443"
PMM_URL = f"https://{PMM_IP}:{PMM_PORT}/v1/qan/metrics:getReport"
PMM_USER = "admin"
PMM_PASSWORD = "superpart1234"
PMM_DB_FILTERS = ["wms", "tms"]

# เปลี่ยนโครงสร้างเป็น LM Studio ตามพอร์ตและโมเดลที่คุณกำหนดไว้
LM_STUDIO_HOST = "http://localhost:1234/v1"
LM_STUDIO_MODEL = "google/gemma-4-e4b" # ใช้ชื่อโมเดลตรงเป๊ะตามที่คุณเปิดรันใน LM Studio

# ช่องทางส่งแจ้งเตือนเข้า LINE (เลือกเปิดใช้งานทีหลังได้)
LINE_NOTIFY_TOKEN = ""

# --- [ 2. ฟังก์ชันดึง Log และกรองข้อมูลจาก Loki ] ---
def fetch_loki_logs():
    print(f"[*] กำลังดึง Log ย้อนหลัง 1 ชั่วโมงจาก Monitoring Server ({LOKI_IP})...")
    
    # ดึง Log ของโปรเจกต์ wms/tms บน production ออกมาวิเคราะห์โครงสร้างประสิทธิภาพ
    projects_regex = "|".join(LOKI_PROJECTS)
    logql_query = f'{{project=~"{projects_regex}", environment="production"}}'
    
    # คำนวณเวลาปัจจุบันและถอยหลังไป 1 ชั่วโมง (60 นาที) ในหน่วย Nanoseconds ตามมาตรฐาน Loki API
    now_ns = int(time.time() * 1000000000)
    start_ns = now_ns - (60 * 60 * 1000000000)
    
    params = {
        'query': logql_query,
        'limit': 30,  # ดึงมา 30 บรรทัดล่าสุดที่มีการบันทึกในระบบ
        'start': start_ns,
        'end': now_ns
    }
    
    try:
        response = requests.get(LOKI_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = data.get('data', {}).get('result', [])
            
            critical_logs = []
            for item in results:
                for val in item.get('values', []):
                    log_text = val[1]
                    
                    # คัดเลือกบรรทัดที่มีนัยสำคัญต่อประสิทธิภาพหรือมี Error โผล่มา
                    if any(x in log_text.lower() for x in ["error", "warn", "status=5", "totaltime:"]):
                        critical_logs.append(log_text)
                        
            # ส่ง Log ให้ AI วิเคราะห์ (ตัดเอาเฉพาะ 15 บรรทัดเด่นๆ ป้องกัน Context ล้น)
            return "\n".join(critical_logs[:15])
        else:
            print(f"[!] Loki Error: ไม่สามารถคิวรีข้อมูลได้ (Status {response.status_code})")
            return None
    except Exception as e:
        print(f"[!] ไม่สามารถเชื่อมต่อไปยัง Loki ({LOKI_IP}): {str(e)}")
        return None

# --- [ 2.1. ฟังก์ชันดึงข้อมูล Slow SQL จาก PMM QAN ] ---
def fetch_pmm_slow_queries(hours=1):
    print(f"[*] กำลังดึงข้อมูล SQL ที่ช้าจาก PMM QAN ({PMM_IP}) ย้อนหลัง {hours} ชั่วโมง...")
    
    now = datetime.utcnow()
    start_time = now - timedelta(hours=hours)
    start_iso = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_iso = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    payload = {
        "columns": ["load", "num_queries", "query_time"],
        "group_by": "queryid",
        "limit": 10,
        "period_start_from": start_iso,
        "period_start_to": end_iso,
        "labels": [
            {"key": "database", "value": PMM_DB_FILTERS}
        ],
        "order_by": "-query_time"
    }
    
    try:
        response = requests.post(PMM_URL, json=payload, auth=(PMM_USER, PMM_PASSWORD), verify=False, timeout=15)
        if response.status_code == 200:
            data = response.json()
            rows = data.get("rows", [])
            
            slow_queries = []
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
                
                slow_queries.append({
                    "query": fingerprint,
                    "avg_time_sec": avg_time,
                    "calls": cnt,
                    "total_time_sec": sum_time,
                    "database": db_name
                })
            
            slow_queries.sort(key=lambda x: x["avg_time_sec"], reverse=True)
            return slow_queries
        else:
            print(f"[!] PMM Error: ไม่สามารถคิวรีข้อมูลได้ (Status {response.status_code})")
            return None
    except Exception as e:
        print(f"[!] ไม่สามารถเชื่อมต่อไปยัง PMM ({PMM_IP}): {str(e)}")
        return None

# --- [ 3. ฟังก์ชันส่งข้อมูลให้ LM Studio วิเคราะห์ ] ---
def analyze_logs_with_lmstudio(logs_text, slow_queries_text):
    if (not logs_text or logs_text.strip() == "") and (not slow_queries_text or slow_queries_text.strip() == ""):
        return "ระบบปกติสุขดี หรือไม่มี Log/Slow Queries ของเงื่อนไข WMS Production บันทึกเข้ามาในช่วง 1 ชั่วโมงที่ผ่านมา"

    # ปรับ Endpoint ยิงไปที่ Chat Completions ของ LM Studio
    api_url = f"{LM_STUDIO_HOST}/chat/completions"
    
    # จัดหน้าตาโครงสร้าง System และ User Message แบบ OpenAI format ที่ LM Studio ต้องการ
    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "คุณคือผู้เชี่ยวชาญด้าน DevOps และ System Administrator หน้าที่ของคุณคือวิเคราะห์คอขวดระบบ ปัญหาประสิทธิภาพ และ Error Log เพื่อหาสาเหตุเชิงลึก"
            },
            {
                "role": "user",
                "content": f"""จงวิเคราะห์ Log ของระบบ WMS/TMS และข้อมูล SQL Slow Queries จาก Percona Monitoring & Management (PMM) ต่อไปนี้ เพื่อระบุแยกแยะจุดคอขวดระหว่าง Network/Frontend, Backend (Spring Boot) และ Database (PostgreSQL) รวมถึงตรวจสอบหา Error ที่ซ่อนอยู่

เกณฑ์การพิจารณาประสิทธิภาพ:
1. หากค่า TotalTime สูง แต่ค่า SpringBootTime ต่ำอย่างเห็นได้ชัด -> สาเหตุเกิดจาก Network Overhead / Frontend
2. หากค่า TotalTime สูง และค่า SpringBootTime สูงในระดับที่ใกล้เคียงกัน -> สาเหตุเกิดจากฝั่ง Backend/API (Spring Boot ทำงานช้า)
3. หากฝั่ง Backend ช้า ให้ตรวจสอบข้อมูล SQL Slow Queries จาก PMM ด้านล่างว่ามีความช้าที่สัมพันธ์กันหรือไม่ (เช่น มี SQL Query ตัวใดที่รันเฉลี่ยช้าและใช้บ่อยในฐานข้อมูล wms)
4. ตรวจสอบว่าในบรรทัดที่เกิดความช้า มีข้อความแจ้งเตือน Error บันทึกอยู่, พ่น HTTP Status 5xx (เช่น 502, 504) หรือมี Exception โผล่มาด้วยหรือไม่

จงสรุปผลวิเคราะห์เป็นภาษาไทยให้กระชับ ตรงประเด็น เป็นข้อๆ (ไม่เกิน 4 ข้อ) โดยระบุชื่อ Endpoint Path และคำสั่ง SQL หรือตารางที่เป็นคอขวดให้ชัดเจน

Logs ที่ระบุพบจากระบบ (Nginx/NPM):
{logs_text}

SQL Slow Queries จาก PMM QAN:
{slow_queries_text}"""
            }
        ],
        "temperature": 0.2, # บังคับให้ AI ยึดตามเนื้อผ้าของ Log จริง
        "stream": False
    }
    
    try:
        response = requests.post(api_url, json=payload, timeout=120)
        if response.status_code == 200:
            # ดึงคำตอบจากโครงสร้าง JSON ของ OpenAI Format
            return response.json()['choices'][0]['message']['content']
        else:
            return f"LM Studio API Error: Status {response.status_code} - {response.text}"
    except Exception as e:
        return f"ไม่สามารถเชื่อมต่อไปยัง LM Studio ได้: {str(e)}"

# --- [ 4. ฟังก์ชันส่งแจ้งเตือนเข้าแอปภายนอก (Optional) ] ---
def send_line_notify(message):
    if not LINE_NOTIFY_TOKEN: 
        return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
    data = {"message": f"\n📊 [AI Dashboard Analyst]\n{message}"}
    try:
        requests.post(url, headers=headers, data=data, timeout=10)
    except Exception as e:
        print(f"[!] ไม่สามารถส่งไลน์แจ้งเตือนได้: {str(e)}")

# --- [ 5. จุดสั่งรันโปรแกรมหลัก ] ---
if __name__ == "__main__":
    raw_logs = fetch_loki_logs()
    slow_queries = fetch_pmm_slow_queries(hours=1)
    
    # Format slow queries text
    slow_queries_text = ""
    if slow_queries:
        for idx, q in enumerate(slow_queries[:10]):
            slow_queries_text += f"\n[{idx+1}] DB: {q.get('database', 'unknown')} | Avg: {q['avg_time_sec']:.4f}s | Calls: {q['calls']} | Total: {q['total_time_sec']:.4f}s\nQuery: {q['query']}\n"
    else:
        slow_queries_text = "ไม่พบ slow queries ในฐานข้อมูล wms/tms หรือเกิดข้อผิดพลาดในการเชื่อมต่อ PMM"
        
    if raw_logs or slow_queries:
        print("[*] ดึงข้อมูลสำเร็จ! กำลังส่งข้อมูลให้ LM Studio ประมวลผลวิเคราะห์...")
        ai_summary = analyze_logs_with_lmstudio(raw_logs or "ไม่พบล็อก Nginx/Loki ที่ตรงตามเกณฑ์ประสิทธิภาพ", slow_queries_text)
        
        print("\n================== ผลลัพธ์การวิเคราะห์โดย AI ==================")
        print(ai_summary)
        print("=========================================================\n")
        
        # คืนค่าบรรทัดด้านล่างหากต้องการให้แจ้งเตือนส่งไลน์
        # send_line_notify(ai_summary)
    else:
        print("[+] ไม่พบข้อมูลล็อกหรือ SQL ที่เข้าเงื่อนไขในช่วง 1 ชั่วโมงนี้")