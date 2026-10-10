from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
import shutil
import subprocess
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError


# 根据 app.py 的位置找到项目根目录。
ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "uploads"
OUTPUTS = ROOT / "outputs"
FRONTEND = ROOT / "frontend"

for directory in (UPLOADS, OUTPUTS, FRONTEND):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Photo to Space")

# 一次只生成一个模型，避免多个任务同时占用内存。
executor = ThreadPoolExecutor(max_workers=1)
jobs = {}
jobs_lock = Lock()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png"}


def update_job(job_id, **changes):
    with jobs_lock:
        jobs[job_id].update(changes)


def get_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在")
        return dict(job)


def generate_model(job_id, image_path, output_dir):
    """在后台运行 SHARP，将日志写入该任务的目录。"""
    update_job(job_id, status="running", message="正在生成模型")

    log_path = output_dir / "sharp.log"
    sharp_command = shutil.which("sharp")

    if sharp_command is None:
        update_job(
            job_id,
            status="failed",
            message="找不到 sharp，请在 sharp Conda 环境中启动后端",
        )
        return

    command = [
        sharp_command,
        "predict",
        "-i", str(image_path),
        "-o", str(output_dir),
        "--no-render",
    ]

    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            result = subprocess.run(
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=ROOT,
                timeout=3600,
                check=False,
            )

        if result.returncode != 0:
            raise RuntimeError(
                f"SHARP 运行失败，退出码：{result.returncode}"
            )

        models = sorted(output_dir.rglob("*.ply"))
        if not models:
            raise RuntimeError("SHARP 已结束，但没有找到 .ply 文件")

        model_path = models[0]

        update_job(
            job_id,
            status="completed",
            message="生成完成",
            model_path=str(model_path),
            model_url=f"/api/jobs/{job_id}/model",
        )

    except subprocess.TimeoutExpired:
        update_job(
            job_id,
            status="failed",
            message="生成超过一小时，任务已停止，请查看日志",
        )
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            message=f"{exc}；请查看任务日志",
        )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "sharp_available": shutil.which("sharp") is not None,
    }


@app.post("/api/upload", status_code=202)
async def upload_image(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in ALLOWED_SUFFIXES:
        await file.close()
        raise HTTPException(400, "请上传 JPG 或 PNG 照片")

    job_id = uuid.uuid4().hex
    upload_dir = UPLOADS / job_id
    output_dir = OUTPUTS / job_id

    upload_dir.mkdir()
    output_dir.mkdir()

    # 固定文件名，避免原始文件名包含特殊字符或路径。
    image_path = upload_dir / f"photo{suffix}"
    total_bytes = 0

    try:
        with image_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)

                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "照片不能超过 20 MB")

                destination.write(chunk)

        if total_bytes == 0:
            raise HTTPException(400, "上传文件为空")

        # 检查实际内容，避免只改扩展名的文件。
        try:
            with Image.open(image_path) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise HTTPException(400, "文件内容必须是 JPG 或 PNG")
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError):
            raise HTTPException(400, "无法读取照片，请换一张图片")

    except Exception:
        shutil.rmtree(upload_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)
        raise
    finally:
        await file.close()

    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "message": "已上传，等待生成",
            "model_url": None,
            "log_url": f"/api/jobs/{job_id}/log",
        }

    executor.submit(generate_model, job_id, image_path, output_dir)

    return get_job(job_id)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    # 内部磁盘路径无需返回给网页。
    job.pop("model_path", None)
    return job


@app.get("/api/jobs/{job_id}/model")
def download_model(job_id: str):
    job = get_job(job_id)

    if job["status"] != "completed":
        raise HTTPException(409, "模型还没有生成完成")

    model_path = Path(job["model_path"])
    if not model_path.is_file():
        raise HTTPException(404, "模型文件不存在")

    return FileResponse(
        model_path,
        media_type="application/octet-stream",
        filename="scene.ply",
    )


@app.get("/api/jobs/{job_id}/log")
def job_log(job_id: str):
    get_job(job_id)
    log_path = OUTPUTS / job_id / "sharp.log"

    if not log_path.exists():
        return {"log": "任务尚未开始"}

    # 返回最后一部分日志，方便排查失败原因。
    with log_path.open("rb") as log_file:
        log_file.seek(0, 2)
        size = log_file.tell()
        log_file.seek(max(0, size - 16000))
        log_text = log_file.read().decode("utf-8", errors="replace")

    return {"log": log_text}


@app.get("/")
def homepage():
    index_path = FRONTEND / "index.html"
    if not index_path.exists() or index_path.stat().st_size == 0:
        return {"message": "后端已启动。先打开 /docs 测试上传接口。"}
    return FileResponse(index_path)


app.mount(
    "/static",
    StaticFiles(directory=FRONTEND),
    name="static",
)