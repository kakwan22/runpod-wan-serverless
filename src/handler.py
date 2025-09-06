import runpod
import json
import requests
import uuid
import base64
import os
import time
import subprocess

def start_comfyui():
    """Start ComfyUI server if not already running"""
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
                        # Return the first MP4 file found
                        with open(mp4_files[0], "rb") as f:
                            video_base64 = base64.b64encode(f.read()).decode()
                        return {
                            "success": True,
                            "video_base64": video_base64,
                            "filename": os.path.basename(mp4_files[0])
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