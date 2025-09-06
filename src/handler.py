import runpod
import json
import requests
import uuid
import base64
import os
import time
import subprocess

def check_model_hash():
    """Check and print model file hashes for debugging"""
    try:
        import hashlib
        
        # Check main model
        model_path = "/ComfyUI/models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors"
        # Note: Your local uses non-NSFW version but RunPod should use NSFW version
        # We need to get the correct hash for the NSFW version
        
        if os.path.exists(model_path):
            # Get full file hash
            hash_md5 = hashlib.md5()
            with open(model_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            
            actual_hash = hash_md5.hexdigest().upper()
            file_size = os.path.getsize(model_path)
            
            print(f"🎬 WAN Model: wan2.2-i2v-rapid-aio-v10-nsfw.safetensors")
            print(f"  📦 Size: {file_size / (1024**3):.2f} GB")
            print(f"  🔍 Hash: {actual_hash}")
        else:
            print(f"❌ WAN model not found at {model_path}")
            
        # Check CLIP vision model
        clip_path = "/ComfyUI/models/clip_vision/clip_vision_vit_h.safetensors"
        expected_clip_hash = "EF7BC1CA20305F80D0E4E1E3B27D9568"  # Your local CLIP hash
        
        if os.path.exists(clip_path):
            hash_md5 = hashlib.md5()
            with open(clip_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            
            actual_clip_hash = hash_md5.hexdigest().upper()
            clip_size = os.path.getsize(clip_path)
            
            print(f"👁️ CLIP Vision: clip_vision_vit_h.safetensors")
            print(f"  📦 Size: {clip_size / (1024**3):.2f} GB")
            print(f"  🔍 Hash: {actual_clip_hash}")
            
            if actual_clip_hash != expected_clip_hash:
                print(f"  ⚠️ CLIP hash mismatch! Expected: {expected_clip_hash}")
        else:
            print(f"❌ CLIP model not found at {clip_path}")
            
    except Exception as e:
        print(f"⚠️ Could not check model hashes: {e}")

def start_comfyui():
    """Start ComfyUI server if not already running"""
    # Check model hash for debugging
    check_model_hash()
    
    # First check if ComfyUI is already running
    try:
        response = requests.get("http://localhost:8188/system_stats", timeout=5)
        if response.ok:
            print("ComfyUI server is already running!")
            return True
    except:
        pass
    
    print("Starting ComfyUI server...")
    
    # Start server in background
    process = subprocess.Popen(
        ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"],
        cwd="/ComfyUI",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for ComfyUI to be ready
    for i in range(30):
        try:
            response = requests.get("http://localhost:8188/system_stats", timeout=5)
            if response.ok:
                print("ComfyUI server is ready!")
                return True
        except:
            pass
        time.sleep(2)
        print(f"Waiting for ComfyUI... ({i+1}/30)")
    
    return False

def handler(job):
    """RunPod serverless handler"""
    try:
        # Start ComfyUI if not running
        if not start_comfyui():
            return {"error": "Failed to start ComfyUI server"}
        
        # Extract job input
        job_input = job.get("input", {})
        workflow = job_input.get("workflow", {})
        client_id = str(uuid.uuid4())
        
        # Clear input directory if requested (cache busting)
        clear_cache = job_input.get("clear_cache", False)
        clear_input_dir = job_input.get("clear_input_dir", False)
        
        if clear_cache or clear_input_dir:
            print("🧹 Clearing ComfyUI input directory to prevent caching...")
            import shutil
            input_dir = "/ComfyUI/input"
            if os.path.exists(input_dir):
                shutil.rmtree(input_dir)
                os.makedirs(input_dir, exist_ok=True)
                print("✅ Input directory cleared!")
        
        # Handle images (your app sends array of image objects)
        images = job_input.get("images", [])
        for image_obj in images:
            image_name = image_obj.get("name")
            image_data = image_obj.get("image")
            
            if image_data and image_name:
                # Strip data URI prefix if present
                if image_data.startswith("data:image"):
                    image_data = image_data.split(",")[1]
                
                # Save image to ComfyUI input directory
                image_bytes = base64.b64decode(image_data)
                os.makedirs("/ComfyUI/input", exist_ok=True)
                
                # Log image hash for debugging
                import hashlib
                image_hash = hashlib.md5(image_bytes).hexdigest()[:16]
                print(f"📷 Saving image {image_name} with hash: {image_hash}")
                
                with open(f"/ComfyUI/input/{image_name}", "wb") as f:
                    f.write(image_bytes)
        
        # Queue workflow to ComfyUI
        queue_response = requests.post("http://localhost:8188/prompt", json={
            "prompt": workflow,
            "client_id": client_id
        })
        
        if not queue_response.ok:
            return {"error": f"Failed to queue workflow: {queue_response.text}"}
        
        # Get prompt ID and wait for completion
        queue_result = queue_response.json()
        prompt_id = queue_result.get("prompt_id")
        
        # Poll for completion (10 minute timeout)
        timeout = 600
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            history_response = requests.get(f"http://localhost:8188/history/{prompt_id}")
            if history_response.ok:
                history = history_response.json()
                if prompt_id in history:
                    # Job completed - find video output
                    result = history[prompt_id]
                    outputs = result.get("outputs", {})
                    
                    print(f"DEBUG: Available outputs: {list(outputs.keys())}")
                    
                    # Check all output nodes for video
                    for node_id, output in outputs.items():
                        print(f"DEBUG: Node {node_id} output keys: {list(output.keys())}")
                        
                        if "videos" in output:
                            video_info = output["videos"][0]
                            video_path = f"/ComfyUI/output/{video_info['filename']}"
                            print(f"DEBUG: Found video at {video_path}")
                            
                            if os.path.exists(video_path):
                                with open(video_path, "rb") as f:
                                    video_base64 = base64.b64encode(f.read()).decode()
                                
                                return {
                                    "success": True,
                                    "video_base64": video_base64,
                                    "filename": video_info['filename']
                                }
                            else:
                                print(f"ERROR: Video file not found at {video_path}")
                    
                    # Also check for any MP4 files in output directory
                    import glob
                    mp4_files = glob.glob("/ComfyUI/output/*.mp4")
                    if mp4_files:
                        print(f"DEBUG: Found MP4 files: {mp4_files}")
                        # Return the most recently modified file (newest)
                        mp4_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                        newest_file = mp4_files[0]
                        print(f"DEBUG: Using newest file: {newest_file}")
                        
                        with open(newest_file, "rb") as f:
                            video_base64 = base64.b64encode(f.read()).decode()
                        return {
                            "success": True,
                            "video_base64": video_base64,
                            "filename": os.path.basename(newest_file)
                        }
                    
                    # Check all possible video locations
                    possible_paths = [
                        "/ComfyUI/output/*.mp4",
                        "/ComfyUI/output/*.avi",
                        "/ComfyUI/output/*.mov",
                        "/ComfyUI/output/**/*.mp4",
                        "/output/*.mp4",
                        "*.mp4"
                    ]
                    
                    for pattern in possible_paths:
                        found_files = glob.glob(pattern, recursive=True)
                        if found_files:
                            print(f"DEBUG: Found video files at {pattern}: {found_files}")
                            with open(found_files[0], "rb") as f:
                                video_base64 = base64.b64encode(f.read()).decode()
                            return {
                                "success": True,
                                "video_base64": video_base64,
                                "filename": os.path.basename(found_files[0])
                            }
                    
                    # If we can't find the video but generation completed, return success
                    # The app will handle finding the video another way
                    print("WARNING: Generation completed but video file not found")
                    return {
                        "success": True,
                        "message": "Generation completed but video location unknown",
                        "outputs": outputs
                    }
            
            time.sleep(3)
        
        return {"error": "Video generation timed out"}
    
    except Exception as e:
        return {"error": f"Handler error: {str(e)}"}

# Initialize RunPod serverless
runpod.serverless.start({"handler": handler})