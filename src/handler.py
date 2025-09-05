import runpod
import json
import requests
import uuid
import base64
import os
import time
import subprocess

def start_comfyui():
    """Start ComfyUI server"""
    print("Starting ComfyUI server...")
    
    # Change to ComfyUI directory and start server
    process = subprocess.Popen(
        ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"],
        cwd="/ComfyUI"
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
                    
                    for node_id, output in outputs.items():
                        if "videos" in output:
                            video_info = output["videos"][0]
                            video_path = f"/ComfyUI/output/{video_info['filename']}"
                            
                            if os.path.exists(video_path):
                                with open(video_path, "rb") as f:
                                    video_base64 = base64.b64encode(f.read()).decode()
                                
                                return {
                                    "success": True,
                                    "video_base64": video_base64,
                                    "filename": video_info['filename']
                                }
                    
                    return {"error": "No video output found"}
            
            time.sleep(3)
        
        return {"error": "Video generation timed out"}
    
    except Exception as e:
        return {"error": f"Handler error: {str(e)}"}

# Initialize RunPod serverless
runpod.serverless.start({"handler": handler})