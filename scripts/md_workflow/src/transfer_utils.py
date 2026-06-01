import os
import shutil
import subprocess
import logging
import json
import re
import requests
import http.client
import urllib.parse
import base64
from datetime import datetime

logger = logging.getLogger(__name__)

def archive_results(directory_path, archive_name=None):
    """
    Creates a zip archive of the specified directory.
    """
    if not os.path.exists(directory_path):
        logger.error(f"Directory not found for archiving: {directory_path}")
        return None
        
    if archive_name is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.basename(directory_path.rstrip("/"))
        archive_name = f"{base_name}_{timestamp}.zip"
    
    if not archive_name.endswith(".zip"):
        archive_name += ".zip"
        
    logger.info(f"Creating archive: {archive_name} from {directory_path}...")
    
    # We use shutil.make_archive which is robust
    # It takes base_name without extension
    output_filename = shutil.make_archive(
        archive_name.replace(".zip", ""), 
        'zip', 
        root_dir=os.path.dirname(os.path.abspath(directory_path)), 
        base_dir=os.path.basename(directory_path.rstrip("/"))
    )
    
    logger.info(f"Archive created: {output_filename}")
    return output_filename

def split_file(file_path, chunk_size_mb=512):
    """
    Splits a file into chunks of specified size in MB using the system 'split' command.
    """
    file_size = os.path.getsize(file_path)
    if file_size <= chunk_size_mb * 1024 * 1024:
        return [file_path]
    
    logger.info(f"File size {file_size / (1024*1024):.2f}MB exceeds {chunk_size_mb}MB, splitting...")
    
    prefix = file_path + ".part"
    cmd = ["split", "-b", f"{chunk_size_mb}M", "-d", file_path, prefix]
    try:
        subprocess.run(cmd, check=True)
        # Find all chunks created
        dir_name = os.path.dirname(file_path)
        base_prefix = os.path.basename(prefix)
        chunks = sorted([os.path.join(dir_name, f) for f in os.listdir(dir_name) if f.startswith(base_prefix)])
        logger.info(f"File split into {len(chunks)} chunks.")
        return chunks
    except Exception as e:
        logger.error(f"Error splitting file: {e}")
        return [file_path]

def upload_to_transfer_sh(file_path):
    """
    Uploads a file to transfer.sh using requests.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found for upload: {file_path}")
        return None
        
    file_name = os.path.basename(file_path)
    logger.info(f"Uploading {file_name} to transfer.sh using requests...")
    
    try:
        with open(file_path, 'rb') as f:
            response = requests.put(
                f"https://transfer.sh/{file_name}", 
                data=f, 
                timeout=600
            )
        
        if response.status_code == 200:
            url = response.text.strip()
            logger.info(f"Upload successful! URL: {url}")
            return url
        else:
            logger.error(f"Upload to transfer.sh failed: Status {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Upload to transfer.sh failed: {e}")
        return None

def upload_to_bashupload(file_path):
    """
    Fallback upload to bashupload.com using requests.
    """
    if not os.path.exists(file_path):
        return None
        
    file_name = os.path.basename(file_path)
    logger.info(f"Uploading {file_name} to bashupload.com using requests...")
    
    try:
        with open(file_path, 'rb') as f:
            # bashupload usually expects a multipart/form-data POST
            files = {'file': (file_name, f)}
            response = requests.post(
                "https://bashupload.com/", 
                files=files, 
                timeout=600
            )
        
        if response.status_code == 200:
            output = response.text
            for line in output.split("\n"):
                if "https://bashupload.com/" in line and file_name in line:
                    urls = re.findall(r'https://bashupload\.com/[^\s<>"]+', line)
                    if urls:
                        logger.info(f"Upload successful! URL: {urls[0]}")
                        return urls[0]
            return None
        else:
            logger.error(f"Upload to bashupload.com failed: Status {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Upload to bashupload.com failed: {e}")
        return None

def upload_via_http_client(file_path):
    """
    Ultimate fallback using standard http.client.
    Only supports transfer.sh (PUT).
    """
    if not os.path.exists(file_path):
        return None
        
    file_name = os.path.basename(file_path)
    logger.info(f"Uploading {file_name} to transfer.sh using http.client...")
    
    try:
        conn = http.client.HTTPSConnection("transfer.sh", timeout=600)
        with open(file_path, "rb") as f:
            data = f.read()
            conn.request("PUT", f"/{file_name}", body=data)
            
        response = conn.getresponse()
        if response.status == 200:
            url = response.read().decode().strip()
            logger.info(f"Upload successful! URL: {url}")
            return url
        return None
    except Exception as e:
        logger.error(f"Upload via http.client failed: {e}")
        return None

def try_upload_with_fallbacks(file_path):
    """Try multiple services and methods for a single file."""
    # 1. Try transfer.sh with requests
    url = upload_to_transfer_sh(file_path)
    if url: return url
    
    # 2. Try bashupload with requests
    url = upload_to_bashupload(file_path)
    if url: return url
    
    # 3. Ultimate fallback: transfer.sh with http.client
    url = upload_via_http_client(file_path)
    return url

def upload_to_gist(file_path, description="MD Workflow Results Manifest"):
    """
    Uploads a file (usually the manifest) to GitHub Gist using direct API calls.
    Requires GITHUB_TOKEN environment variable.
    """
    if not os.path.exists(file_path):
        return None
        
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN environment variable not set. Skipping Gist upload.")
        return None
        
    file_name = os.path.basename(file_path)
    logger.info(f"Uploading {file_name} to GitHub Gist via API...")
    
    try:
        with open(file_path, "r") as f:
            content = f.read()
            
        payload = {
            "description": description,
            "public": True,
            "files": {
                file_name: {
                    "content": content
                }
            }
        }
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.post(
            "https://api.github.com/gists",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 201:
            url = response.json().get("html_url")
            logger.info(f"Gist created successfully via API! URL: {url}")
            return url
        else:
            logger.error(f"GitHub API Gist creation failed: Status {response.status_code}, {response.text}")
            return None
    except Exception as e:
        logger.error(f"Gist API upload failed: {e}")
        return None

def upload_all_to_gist(archive_path, chunks, manifest):
    """
    Ultimate fallback: Uploads all chunks and the manifest to a single Gist repository.
    The chunks are base64 encoded because Gists are primarily for text.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN not set. Cannot use Ultimate Gist Fallback.")
        return None
        
    logger.info(f"Initiating Ultimate Fallback: Uploading {len(chunks)} chunks to a single Gist...")
    
    manifest["fallback_gist_mode"] = True
    manifest["encoding"] = "base64"
    manifest["note"] = "Chunks are base64 encoded in this Gist. Decode before use (e.g., 'base64 -d <file>')."
    
    payload = {
        "description": f"MD Results Ultimate Backup: {os.path.basename(archive_path)}",
        "public": True,
        "files": {
            "manifest.json": {
                "content": json.dumps(manifest, indent=4)
            }
        }
    }
    
    for i, chunk_path in enumerate(chunks):
        chunk_name = os.path.basename(chunk_path)
        logger.info(f"Encoding {chunk_name} for Gist...")
        try:
            with open(chunk_path, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode("utf-8")
            payload["files"][chunk_name] = {"content": b64_content}
        except Exception as e:
            logger.error(f"Failed to encode chunk {chunk_name}: {e}")
            return None
        
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        logger.info("Sending payload to GitHub Gist API...")
        response = requests.post(
            "https://api.github.com/gists",
            json=payload,
            headers=headers,
            timeout=1200  # Generous timeout for large payloads
        )
        
        if response.status_code == 201:
            url = response.json().get("html_url")
            logger.info(f"Ultimate Fallback Successful! Master Gist URL: {url}")
            return url
        else:
            logger.error(f"Ultimate Fallback Gist creation failed: Status {response.status_code}, {response.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Ultimate Fallback Gist upload failed: {e}")
        return None

def perform_chunked_upload(archive_path, chunk_size_mb):
    """
    Internal helper to perform chunked upload with a specific chunk size.
    """
    chunks = split_file(archive_path, chunk_size_mb)
    
    manifest = {
        "original_file": os.path.basename(archive_path),
        "timestamp": datetime.now().isoformat(),
        "total_chunks": len(chunks),
        "chunk_size_mb": chunk_size_mb,
        "chunks": []
    }
    
    success = True
    uploaded_chunks = []
    
    try:
        for i, chunk_path in enumerate(chunks):
            # For chunks, we still use normal file uploads
            url = try_upload_with_fallbacks(chunk_path)
            if url:
                manifest["chunks"].append({
                    "part": i,
                    "filename": os.path.basename(chunk_path),
                    "url": url
                })
                uploaded_chunks.append(chunk_path)
            else:
                logger.error(f"Failed to upload chunk {i}: {chunk_path}")
                success = False
                break
                
        if success:
            if len(chunks) == 1:
                return manifest["chunks"][0]["url"]
            else:
                manifest_path = archive_path + ".manifest.json"
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f, indent=4)
                
                logger.info(f"Uploading manifest to Gist: {manifest_path}")
                # Use Gist for the manifest as requested
                url = upload_to_gist(manifest_path, f"Manifest for {os.path.basename(archive_path)}")
                
                # Fallback to normal upload if Gist fails
                if not url:
                    url = try_upload_with_fallbacks(manifest_path)
                
                try:
                    os.remove(manifest_path)
                except:
                    pass
                return url
        else:
            # Ultimate Fallback: if normal chunk uploads fail, use the Gist directly for all chunks
            logger.warning("Standard cloud services failed. Triggering Ultimate Gist Fallback for all chunks...")
            fallback_url = upload_all_to_gist(archive_path, chunks, manifest)
            return fallback_url
    finally:
        # Clean up chunks
        for chunk in uploaded_chunks:
            if chunk != archive_path:
                try:
                    os.remove(chunk)
                except:
                    pass
        # Clean up any remaining chunks that weren't uploaded in case of failure
        for chunk in chunks:
            if chunk != archive_path and os.path.exists(chunk):
                try:
                    os.remove(chunk)
                except:
                    pass
                    
    return None

def archive_and_upload(directory_path):
    """
    Combined helper to archive and upload with adaptive chunking (512MB, 128MB, 64MB).
    """
    archive = archive_results(directory_path)
    if not archive:
        return None
    
    # Try with progressively smaller chunks if upload fails
    for chunk_size in [512, 128, 64]:
        logger.info(f"Attempting upload with {chunk_size}MB chunks...")
        url = perform_chunked_upload(archive, chunk_size)
        if url:
            print("\n" + "="*50)
            print(f"RESULTS UPLOADED SUCCESSFULLY")
            print(f"URL: {url}")
            print("="*50 + "\n")
            
            # Clean up the original archive after successful upload
            try:
                os.remove(archive)
            except:
                pass
            return url
        
        logger.warning(f"Upload failed with {chunk_size}MB chunks. Retrying with smaller size...")

    logger.error("All upload attempts failed.")
    return None
