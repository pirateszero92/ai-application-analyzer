import os
import io
import json
from minio import Minio
from minio.error import S3Error

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "ai-analyzer-reports")
# Whether to use SSL when connecting to Minio (default to False locally)
MINIO_SECURE = os.getenv("MINIO_SECURE", "False").lower() in ("true", "1", "yes")

_client = None

def get_minio_client():
    global _client
    if _client is None:
        try:
            _client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE
            )
            # Create bucket if it doesn't exist
            if not _client.bucket_exists(MINIO_BUCKET):
                _client.make_bucket(MINIO_BUCKET)
                print(f"[*] Created Minio bucket: {MINIO_BUCKET}")
        except Exception as e:
            print(f"[!] Failed to initialize Minio client: {str(e)}")
            return None
    return _client

def upload_report_archive(report_id: int, logs_text: str, slow_queries_text: str, prometheus_metrics_text: str, summary: str) -> str:
    client = get_minio_client()
    if not client:
        return None
    
    # Structure the archive content
    archive_data = {
        "report_id": report_id,
        "logs_text": logs_text,
        "slow_queries_text": slow_queries_text,
        "prometheus_metrics_text": prometheus_metrics_text,
        "ai_summary": summary
    }
    
    # Convert to JSON string
    json_bytes = json.dumps(archive_data, indent=2, ensure_ascii=False).encode('utf-8')
    stream = io.BytesIO(json_bytes)
    
    object_name = f"reports/report_{report_id}.json"
    
    try:
        client.put_object(
            MINIO_BUCKET,
            object_name,
            stream,
            length=len(json_bytes),
            content_type="application/json"
        )
        return object_name
    except S3Error as e:
        print(f"[!] Minio upload failed: {str(e)}")
        return None

def get_report_archive(object_name: str) -> dict:
    client = get_minio_client()
    if not client:
        return None
    
    try:
        response = client.get_object(MINIO_BUCKET, object_name)
        data = response.read().decode('utf-8')
        return json.loads(data)
    except Exception as e:
        print(f"[!] Minio download failed: {str(e)}")
        return None
