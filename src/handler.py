import runpod
import json
import requests
import uuid
import base64
import os
import time
import subprocess
import hashlib
import shutil
import glob
import random
from typing import Optional, Dict, Any

def start_comfyui():
    """Start ComfyUI server if not already running"""
    try:
        # First check if ComfyUI is already running
        response = requests.get("http://localhost:8188/system_stats", timeout=2)
        if response.status_code == 200:
            print("ComfyUI server is already running!")
            return True
    except requests.exceptions.RequestException:
        pass

    print("Starting ComfyUI server...")
    
    # Start ComfyUI in background
    process = subprocess.Popen([
        "python", "main.py", "--listen", "--force-fp16", "--disable-xformers", "--enable-cors-header"
    ], 
        cwd="/ComfyUI",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for ComfyUI to be ready
    for i in range(30):  # Wait up to 30 seconds
        try:
            response = requests.get("http://localhost:8188/system_stats", timeout=2)
            if response.status_code == 200:
                print("ComfyUI server is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        
        print(f"Waiting for ComfyUI... ({i+1}/30)")
        time.sleep(1)
    
    return False

def calculate_optimal_resolution(original_width: int, original_height: int, target_total_pixels: int = 512*512) -> tuple:
    """Calculate optimal resolution maintaining aspect ratio"""
    aspect_ratio = original_width / original_height
    
    if aspect_ratio > 1:  # Landscape
        height = int((target_total_pixels / aspect_ratio) ** 0.5)
        width = int(height * aspect_ratio)
    else:  # Portrait or square
        width = int((target_total_pixels * aspect_ratio) ** 0.5)
        height = int(width / aspect_ratio)
    
    # Round to nearest multiple of 8 for better compatibility
    width = ((width + 7) // 8) * 8
    height = ((height + 7) // 8) * 8
    
    return width, height

def create_comfyui_workflow(image_name: str, settings: Dict[str, Any]) -> Dict:
    """Create ComfyUI workflow for WAN 2.2 video generation"""
    
    # Handle resolution settings
    if settings.get('resolution') in ['720p', '1080p']:
        if settings['resolution'] == '720p':
            target_width, target_height = 640, 640  # Square 720p equivalent
        else:  # 1080p
            target_width, target_height = 1024, 1024  # Square 1080p equivalent
    elif settings.get('resolution') == 'auto':
        target_width, target_height = 768, 512  # Default fallback
    else:
        # Parse custom resolution or use default
        resolution = settings.get('resolution', '768x512')
        if 'x' in resolution:
            width_str, height_str = resolution.split('x')
            target_width = int(width_str)
            target_height = int(height_str)
        else:
            target_width, target_height = 768, 512
    
    # Video generation parameters
    length = (settings.get('duration', 5) * settings.get('fps', 24))  # frames
    seed = settings.get('seed', random.randint(0, 1000000))
    
    # Workflow structure matching the working local version
    workflow = {
        "1": {
            "inputs": {
                "image": image_name,
                "choose file to upload": "image"
            },
            "class_type": "LoadImage"
        },
        "2": {
            "inputs": {
                "ckpt_name": "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "3": {
            "inputs": {
                "clip_name": "clip_vision_vit_h.safetensors"
            },
            "class_type": "CLIPVisionLoader"
        },
        "4": {
            "inputs": {
                "crop": "center",
                "image": ["1", 0],
                "clip_vision": ["3", 0]
            },
            "class_type": "CLIPVisionEncode"
        },
        "5": {
            "inputs": {
                "text": settings.get('prompt', ''),
                "clip": ["2", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "6": {
            "inputs": {
                "text": settings.get('negativePrompt', ''),
                "clip": ["2", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "shift": settings.get('modelShift', 8.0),
                "model": ["2", 0]
            },
            "class_type": "ModelSamplingSD3"
        },
        "8": {
            "inputs": {
                "positive": ["5", 0],
                "negative": ["6", 0],
                "vae": ["2", 2],
                "clip_vision_output": ["4", 0],
                "start_image": ["1", 0],
                "width": target_width,
                "height": target_height,
                "length": length,
                "batch_size": 1
            },
            "class_type": "WanImageToVideo"
        },
        "9": {
            "inputs": {
                "seed": seed,
                "steps": settings.get('steps', 4),
                "cfg": settings.get('cfg', 1.0),
                "sampler_name": settings.get('samplerMethod', 'sa_solver'),
                "scheduler": settings.get('scheduler', 'beta'),
                "denoise": settings.get('denoise', 1.0),
                "model": ["7", 0],
                "positive": ["8", 0],
                "negative": ["8", 1],
                "latent_image": ["8", 2]
            },
            "class_type": "KSampler"
        },
        "10": {
            "inputs": {
                "samples": ["9", 0],
                "vae": ["2", 2]
            },
            "class_type": "VAEDecode"
        },
        "11": {
            "inputs": {
                "images": ["10", 0],
                "frame_rate": settings.get('fps', 24),
                "loop_count": 0,
                "filename_prefix": "runpod_video",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p", 
                "crf": settings.get('crf', 19),
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            },
            "class_type": "VHS_VideoCombine"
        }
    }
    
    return workflow

def handler(job):
    """RunPod serverless handler for Video Generator App"""
    try:
        print("🚀 Handler starting...")
        
        # Collect debug info to return in response
        debug_info = {"handler_version": "2025-01-07", "job_id": job.get("id", "unknown")}
        
        # Validate required models (no volume, models downloaded in Docker build)
        required_models = {
            "wan_model": "/ComfyUI/models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors",
            # VAE is built into the checkpoint, no separate file needed
            "clip_vision": "/ComfyUI/models/clip_vision/clip_vision_vit_h.safetensors"
        }
        
        # Check models
        missing_models = []
        for model_name, model_path in required_models.items():
            if not os.path.exists(model_path):
                missing_models.append(f"{model_name} ({model_path})")
                debug_info[f"{model_name}_status"] = "NOT FOUND"
                print(f"❌ Missing model: {model_path}")
            else:
                file_size = os.path.getsize(model_path)
                debug_info[f"{model_name}_status"] = f"OK ({file_size / (1024**3):.2f} GB)"
                print(f"✅ Found {model_name} ({file_size / (1024**3):.2f} GB)")
        
        if missing_models:
            return {
                "error": f"Missing required models: {', '.join(missing_models)}",
                "debug": debug_info
            }
        
        # Start ComfyUI if not running
        if not start_comfyui():
            return {"error": "Failed to start ComfyUI server", "debug": debug_info}
        
        # Extract job input from our Video Generator App
        job_input = job.get("input", {})
        
        # Get image data and settings from our app
        # Handle both old format (direct fields) and new format (images array)
        images_array = job_input.get("images", [])
        if images_array and len(images_array) > 0:
            print(f"🔍 Using new format: images array with {len(images_array)} images")
            first_image = images_array[0]
            image_data = first_image.get("image_data", "")
            image_name = first_image.get("image_name", "input_image.png")
            print(f"📷 Handler debug: image_data length: {len(image_data)}, image_name: {image_name}")
        else:
            # Fallback for old format
            print("🔍 Using old format: direct image fields")
            image_data = job_input.get("image_data", job_input.get("image", ""))
            image_name = job_input.get("image_name", "input_image.png")
        
        # Get workflow and settings
        workflow = job_input.get("workflow")
        settings = job_input.get("settings", {})
        
        if not image_data:
            return {"error": "No image data provided", "debug": debug_info}
        
        # Save image to ComfyUI input directory
        input_dir = "/ComfyUI/input"
        if os.path.exists(input_dir):
            shutil.rmtree(input_dir)
            os.makedirs(input_dir)
            print("🧹 Cleared ComfyUI input directory")
        else:
            os.makedirs(input_dir, exist_ok=True)
            
        # Decode and save image
        try:
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            
            image_bytes = base64.b64decode(image_data)
            image_path = os.path.join(input_dir, image_name)
            
            with open(image_path, 'wb') as f:
                f.write(image_bytes)
            
            print(f"📷 Saved image: {image_name} ({len(image_bytes)} bytes)")
            
        except Exception as e:
            return {"error": f"Failed to save image: {str(e)}", "debug": debug_info}
        
        # Use provided workflow or create fallback
        if workflow:
            print(f"✅ Using client-provided workflow with {len(workflow)} nodes")
        else:
            # Auto-calculate resolution for fallback
            if settings.get('resolution') == 'auto':
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(image_bytes))
                    calculated_width, calculated_height = calculate_optimal_resolution(img.width, img.height)
                    calculated_resolution = f"{calculated_width}x{calculated_height}"
                    settings['resolution'] = calculated_resolution
                    debug_info['calculated_resolution'] = calculated_resolution
                    print(f"🎯 Auto-calculated resolution: {calculated_resolution} for {img.width}x{img.height} input")
                except Exception as e:
                    print(f"⚠️ Failed to auto-calculate resolution: {e}")
                    settings['resolution'] = "768x512"  # Fallback
            
            # Create workflow as fallback
            workflow = create_comfyui_workflow(image_name, settings)
        
        client_id = str(uuid.uuid4())
        
        # Queue workflow to ComfyUI
        print("📤 Queuing workflow...")
        queue_response = requests.post("http://localhost:8188/prompt", json={
            "prompt": workflow,
            "client_id": client_id
        })
        
        if not queue_response.ok:
            return {
                "error": f"Failed to queue workflow: {queue_response.text}",
                "debug": debug_info
            }
        
        # Get prompt ID and wait for completion
        queue_result = queue_response.json()
        prompt_id = queue_result.get("prompt_id")
        print(f"✅ Queued with prompt_id: {prompt_id}")
        
        if not prompt_id:
            return {"error": "No prompt_id returned", "debug": debug_info}
        
        # Poll for completion with intelligent timeout and error handling
        max_wait_time = 600  # 10 minutes maximum
        start_time = time.time()
        check_interval = 3
        last_progress_time = start_time
        
        while time.time() - start_time < max_wait_time:
            elapsed = int(time.time() - start_time)
            
            # Check job status in history
            try:
                history_response = requests.get(f"http://localhost:8188/history/{prompt_id}", timeout=10)
                if history_response.ok:
                    history = history_response.json()
                    if prompt_id in history:
                        # Job completed - process results
                        result = history[prompt_id]
                        # Check for errors
                        status = result.get("status", {})
                        if status.get("status_str") == "error":
                            error_msg = "Workflow failed"
                            if "messages" in status:
                                for msg in status["messages"]:
                                    if msg[0] == "execution_error":
                                        error_msg = f"Node {msg[1]['node_id']} ({msg[1]['node_type']}): {msg[1]['exception_message']}"
                                        break
                            print(f"❌ {error_msg}")
                            return {"error": error_msg, "debug": debug_info}
                        
                        outputs = result.get("outputs", {})
                        print(f"✅ Job completed - checking for video...")
                        
                        # Get the newest .mp4 file  
                        try:
                            mp4_files = glob.glob("/ComfyUI/output/*.mp4")
                            
                            if mp4_files:
                                video_path = max(mp4_files, key=os.path.getmtime)
                                print(f"✅ Found video: {os.path.basename(video_path)}")
                                
                                with open(video_path, "rb") as f:
                                    video_base64 = base64.b64encode(f.read()).decode()
                                
                                return {
                                    "success": True,
                                    "video_base64": video_base64,
                                    "filename": os.path.basename(video_path),
                                    "resolution": settings.get('resolution', 'Unknown'),
                                    "duration": elapsed,
                                    "debug": debug_info
                                }
                            else:
                                all_files = os.listdir("/ComfyUI/output/")
                                print(f"❌ No video generated. Files: {all_files}")
                                return {
                                    "error": "No video file generated",
                                    "debug": {**debug_info, "output_files": all_files}
                                }
                                
                        except Exception as e:
                            return {
                                "error": f"Could not read output directory: {str(e)}",
                                "debug": debug_info
                            }
                        
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Error checking job status: {e}")
            
            # Print progress every 30 seconds
            if elapsed > 0 and elapsed % 30 == 0:
                print(f"⏳ Generating... ({elapsed}s)")
                
            time.sleep(check_interval)
        
        return {
            "error": f"Video generation timed out after {max_wait_time} seconds",
            "debug": debug_info
        }
    
    except Exception as e:
        return {"error": f"Handler error: {str(e)}"}
    finally:
        # Always cleanup after job completion or failure
        try:
            print("🧹 Performing cleanup after job...")
            # Clear ComfyUI queue
            requests.post("http://localhost:8188/queue", json={"clear": True}, timeout=5)
            # Free GPU memory
            requests.post("http://localhost:8188/free", json={"unload_models": True, "free_memory": True}, timeout=5)
            print("✅ Cleanup completed")
        except:
            pass  # Cleanup failures are not critical

# Initialize RunPod serverless
runpod.serverless.start({"handler": handler})