from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import subprocess
import json
import glob
from datetime import datetime
from typing import Dict, Any

app = FastAPI(title="MD Workflow Monitor")

# Paths from environment variables
OUTDIR = os.environ.get("OUTDIR", "/app/results")
WORKDIR = os.environ.get("WORKDIR", "/app/work")
CONFIG_FILE = os.environ.get("CONFIG_FILE", "/app/config.json")

# Ensure static directory exists
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "status": "running",
        "container_info": {
            "outdir": OUTDIR,
            "workdir": WORKDIR,
            "config": CONFIG_FILE,
            "gpu": os.environ.get("USE_GPU", "unknown"),
            "hostname": os.environ.get("HOSTNAME", "unknown"),
        },
        "message": "Frontend not found. Please ensure static/index.html exists.",
    }


@app.get("/gpu")
async def gpu_status():
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        return {"output": result.stdout}
    except Exception as e:
        return {"error": str(e)}


@app.get("/download/{filename:path}")
async def download_file(filename: str):
    file_path = os.path.join(OUTDIR, filename)
    work_path = os.path.join(WORKDIR, filename)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path, filename=os.path.basename(file_path))
    if os.path.exists(work_path) and os.path.isfile(work_path):
        return FileResponse(work_path, filename=os.path.basename(work_path))
    raise HTTPException(status_code=404, detail="File not found")


def file_stats(name):
    file = os.stat(name)
    return {
        "size": file.st_size,
        "perms": oct(file.st_mode),
        "owner": file.st_uid,
        "group": file.st_gid,
        "accessed": datetime.fromtimestamp(file.st_atime),
        "modified": datetime.fromtimestamp(file.st_mtime),
        "created": datetime.fromtimestamp(file.st_ctime),
    }


@app.get("/checkpoint")
async def cpt_status():
    import re

    CHECKPOINT_REGEX = re.compile(
        r"Writing checkpoint, step (\d+) at ([A-Za-z]{3}\s+[A-Za-z]{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})"
    )
    try:
        log_files = glob.glob(os.path.join(OUTDIR, "*_md.log")) + glob.glob(
            os.path.join(WORKDIR, "*_md.log")
        )
        progress = {}

        for log in log_files:
            complex_id = os.path.basename(log).replace("_md.log", "")
            progress[complex_id] = {
                "timeline": [],
                "checkpoint_file": None,
                "previous_checkpoint_file": None,
            }
            try:
                timeline_events = []
                with open(log, "r") as f:
                    for line in f:
                        match = CHECKPOINT_REGEX.search(line)
                        if match:
                            step = int(match.group(1))
                            timestamp_str = match.group(2)
                            clean_timestamp = re.sub(r"\s+", " ", timestamp_str)

                            timeline_events.append(
                                {"step": step, "timestamp": clean_timestamp}
                            )

                progress[complex_id]["timeline"] = timeline_events

            except Exception as e:
                progress[complex_id]["timeline"] = f"Error parsing log: {str(e)}"

            cpt_file = log.replace(".log", ".cpt")
            if os.path.exists(cpt_file):
                progress[complex_id]["checkpoint_file"] = file_stats(cpt_file)

            prev_cpt_file = cpt_file.replace(".cpt", "_prev.cpt")
            if os.path.exists(prev_cpt_file):
                progress[complex_id]["previous_checkpoint_file"] = file_stats(
                    prev_cpt_file
                )

        return progress

    except Exception as e:
        return {"error": str(e)}


@app.get("/logs")
async def get_logs():
    log_files = glob.glob(os.path.join(OUTDIR, "*.log")) + glob.glob(
        os.path.join(WORKDIR, "*.log")
    )
    logs = {}
    for log in log_files:
        with open(log, "r") as f:
            # Return last 100 lines
            logs[os.path.basename(log)] = f.readlines()[-100:]
    return logs


@app.get("/work")
async def list_work():
    try:
        total_size = 0
        files = []
        for root, dirs, filenames in os.walk(WORKDIR):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                display_path = os.path.relpath(full_path, WORKDIR)
                stats = file_stats(full_path)
                total_size += stats["size"]
                files.append(
                    {
                        "filepath": display_path,
                        "stats": stats,
                    }
                )

        return {"files": files, "total_size": total_size}

    except Exception as e:
        return {"error": f"Failed to read work directory: {str(e)}"}


@app.get("/results")
async def list_results():
    try:
        total_size = 0
        files = []
        for root, dirs, filenames in os.walk(OUTDIR):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                display_path = os.path.relpath(full_path, OUTDIR)
                stats = file_stats(full_path)
                total_size += stats["size"]
                files.append(
                    {
                        "filepath": display_path,
                        "stats": stats,
                    }
                )

        return {"files": files, "total_size": total_size}

    except Exception as e:
        return {"error": f"Failed to read results directory: {str(e)}"}


@app.get("/progress")
async def get_progress():
    import re

    log_files = glob.glob(os.path.join(OUTDIR, "*_md.log")) + glob.glob(
        os.path.join(WORKDIR, "*_md.log")
    )
    progress = {}
    for log in log_files:
        complex_id = os.path.basename(log).replace("_md.log", "")
        try:
            # Use tail and grep to find the last step info
            cmd = (
                f'grep -A 1 "Step" {log} | grep -v "Step" | grep -v "\\--" | tail -n 1'
            )
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            line = result.stdout.strip()
            if line:
                numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
                if len(numbers) >= 2:
                    step = numbers[0]
                    sim_time = float(numbers[1])
                    progress[complex_id] = {
                        "step": step,
                        "time_ps": sim_time,
                        "time_ns": sim_time / 1000.0,
                        "last_update": datetime.fromtimestamp(
                            os.path.getmtime(log)
                        ).isoformat(),
                    }
        except Exception as e:
            progress[complex_id] = {"error": str(e)}
    return progress


@app.get("/config")
async def get_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception as e:
                return {"error": f"Failed to parse config as JSON. {str(e)}"}
    return {"error": "Config file not found"}


@app.post("/notify")
async def trigger_notify(message: str):
    try:
        from src.notify_utils import Notifier

        # We need to load config to get credentials
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)

        notifier = Notifier(cfg.get("notifications", {}))
        if notifier.is_configured():
            notifier.notify(message)
            return {"status": "sent", "message": message}
        else:
            return {"status": "error", "message": "Notifier not configured"}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("WEB_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
