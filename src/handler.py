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

def calculate_optimal_resolution(image_width: int, image_height: int) -> str:
    """Calculate optimal resolution for WAN 2.2 model based on input image"""
    # WAN 2.2 supported resolutions (width x height)
    supported_resolutions = [
        (512, 512), (768, 512), (512, 768),
        (1024, 576), (576, 1024), (768, 768),
        (1024, 768), (768, 1024)
    ]
    
    # Calculate aspect ratio of input
    input_aspect = image_width / image_height
    
    # Find best matching resolution
    best_match = None
    best_score = float('inf')
    
    for width, height in supported_resolutions:
        resolution_aspect = width / height
        
        # Score based on aspect ratio difference and total pixel count
        aspect_diff = abs(input_aspect - resolution_aspect)
        pixel_diff = abs((width * height) - (image_width * image_height)) / (image_width * image_height)
        
        score = aspect_diff + pixel_diff * 0.1  # Weight pixel count less than aspect ratio
        
        if score < best_score:
            best_score = score
            best_match = (width, height)
    
    return f"{best_match[0]}x{best_match[1]}" if best_match else "512x512"

def create_comfyui_workflow(image_name: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Create ComfyUI workflow for WAN 2.2 video generation"""
    
    # Calculate resolution if auto
    resolution = settings.get('resolution', 'auto')
    if resolution == 'auto':
        # For now, use a default. In production, we'd analyze the actual image
        resolution = "768x512"  # Will be calculated from actual image dimensions
    
    # Parse resolution
    width, height = map(int, resolution.split('x'))
    
    # Ensure seed is valid
    seed = settings.get('seed', -1)
    if seed < 0:
        seed = random.randint(0, 1000000)
    
    # Calculate frames/length from duration and FPS
    fps = settings.get('fps', 24)
    duration = settings.get('duration', 5)
    length = int(duration * fps)
    
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
                "width": width,
                "height": height,
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
                "save_output": True,
                "optimize": True
            },
            "class_type": "VHS_VideoCombine"
        }
    }
    
    return workflow

def handler(job):
    """RunPod serverless handler for Video Generator App"""
    try:
        print("🚀 Video Generator Handler Version: 2025-01-07")
        
        # Collect debug info to return in response
        debug_info = {"handler_version": "2025-01-07", "job_id": job.get("id", "unknown")}
        
        # Validate required models (no volume, models downloaded in Docker build)
        required_models = {
            "wan_model": "/ComfyUI/models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors",
            # VAE is built into the checkpoint, no separate file needed
            "clip_vision": "/ComfyUI/models/clip_vision/clip_vision_vit_h.safetensors"
        }
        
        missing_models = []
        for model_name, model_path in required_models.items():
            if not os.path.exists(model_path):
                missing_models.append(f"{model_name} ({model_path})")
                debug_info[f"{model_name}_status"] = "NOT FOUND"
                print(f"❌ Missing model: {model_path}")
            else:
                file_size = os.path.getsize(model_path)
                debug_info[f"{model_name}_status"] = f"OK ({file_size / (1024**3):.2f} GB)"
                print(f"✅ Found model: {model_path} ({file_size / (1024**3):.2f} GB)")
        
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
            # New format: images array
            image_data = images_array[0].get("image")
            image_name = images_array[0].get("name", f"input_{int(time.time())}.png")
            settings = job_input.get("settings", {})
            print(f"🔍 Using new format: images array with {len(images_array)} images")
        else:
            # Old format: direct fields (fallback)
            image_data = job_input.get("image")
            image_name = job_input.get("imageName", f"input_{int(time.time())}.png") 
            settings = job_input.get("settings", {})
            print(f"🔍 Using old format: direct fields")
        
        print(f"🔍 Handler debug: image_data length: {len(image_data) if image_data else 0}, image_name: {image_name}")
        
        if not image_data:
            return {"error": "No image data provided", "debug": debug_info}
        
        # Clean input directory for fresh processing (prevents using old images)
        input_dir = "/ComfyUI/input"
        try:
            if os.path.exists(input_dir):
                shutil.rmtree(input_dir)
                print("🧹 Cleared ComfyUI input directory")
            os.makedirs(input_dir, exist_ok=True)
        except Exception as e:
            print(f"⚠️ Could not clear input directory: {e}")
            # Try to at least create the directory
            os.makedirs(input_dir, exist_ok=True)
        
        # Process image data
        try:
            # Strip data URI prefix if present
            if image_data.startswith("data:image"):
                image_data = image_data.split(",")[1]
            
            # Decode and save image
            image_bytes = base64.b64decode(image_data)
            image_path = f"{input_dir}/{image_name}"
            
            with open(image_path, "wb") as f:
                f.write(image_bytes)
                
            print(f"📷 Saved image: {image_name} ({len(image_bytes)} bytes)")
            
        except Exception as e:
            return {"error": f"Failed to process image: {str(e)}", "debug": debug_info}
        
        # Use the workflow provided by the client, or create one as fallback
        workflow = job_input.get("workflow")
        if not workflow:
            print("⚠️ No workflow provided by client, creating default workflow")
            # Auto-calculate resolution if needed
            if settings.get('resolution') == 'auto':
                try:
                    from PIL import Image
                    with Image.open(image_path) as img:
                        calculated_resolution = calculate_optimal_resolution(img.width, img.height)
                        settings['resolution'] = calculated_resolution
                        debug_info['calculated_resolution'] = calculated_resolution
                        print(f"🎯 Auto-calculated resolution: {calculated_resolution} for {img.width}x{img.height} input")
                except Exception as e:
                    print(f"⚠️ Failed to auto-calculate resolution: {e}")
                    settings['resolution'] = "768x512"  # Fallback
            
            # Create workflow as fallback
            workflow = create_comfyui_workflow(image_name, settings)
        else:
            print(f"✅ Using client-provided workflow with {len(workflow)} nodes")
        
        client_id = str(uuid.uuid4())
        
        # Queue workflow to ComfyUI
        print("🎬 Queuing video generation workflow...")
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
        print(f"📋 Queued job with prompt_id: {prompt_id}")
        
        # Poll for completion with intelligent timeout and error handling
        max_wait_time = 600  # 10 minutes maximum
        start_time = time.time()
        check_interval = 3
        last_progress_time = start_time
        
        while time.time() - start_time < max_wait_time:
            elapsed = int(time.time() - start_time)
            
            # Check if ComfyUI is still responsive
            try:
                health_check = requests.get("http://localhost:8188/system_stats", timeout=10)
                if not health_check.ok:
                    return {
                        "error": "ComfyUI server became unresponsive",
                        "debug": debug_info
                    }
            except requests.exceptions.RequestException as e:
                return {
                    "error": f"ComfyUI server connection lost: {str(e)}",
                    "debug": debug_info
                }
            
            # Check job status in history
            try:
                history_response = requests.get(f"http://localhost:8188/history/{prompt_id}", timeout=10)
                if history_response.ok:
                    history = history_response.json()
                    if prompt_id in history:
                        # Job completed - process results
                        result = history[prompt_id]
                        
                        # Check for errors in the workflow execution
                        status = result.get("status", {})
                        if "error" in status:
                            return {
                                "error": f"Workflow failed: {status['error']}",
                                "debug": debug_info
                            }
                        
                        outputs = result.get("outputs", {})
                        print(f"✅ Job completed! Processing outputs from nodes: {list(outputs.keys())}")
                        
                        # Debug: print all outputs to understand structure
                        print(f"🔍 Output structure: {json.dumps(outputs, indent=2, default=str)[:500]}")
                        
                        # Find video output from VideoHelperSuite node (node 11)
                        video_found = False
                        
                        # Check node 11 specifically (VHS_VideoCombine)
                        if "11" in outputs:
                            print(f"🔍 Node 11 output: {outputs['11']}")
                            node_output = outputs["11"]
                            if isinstance(node_output, dict) and "videos" in node_output:
                                video_info = node_output["videos"][0]
                                video_path = f"/ComfyUI/output/{video_info['filename']}"
                            elif isinstance(node_output, dict) and "video" in node_output:
                                video_info = node_output["video"][0] if isinstance(node_output["video"], list) else node_output["video"]
                                video_path = f"/ComfyUI/output/{video_info.get('filename', 'runpod_video_00001.mp4')}"
                            else:
                                # VHS might not return video info, just save directly
                                print("⚠️ Node 11 doesn't have video info, checking for files...")
                        
                        # Also check all nodes for video output
                        for node_id, output in outputs.items():
                            if "videos" in output and output["videos"]:
                                video_info = output["videos"][0]
                                video_path = f"/ComfyUI/output/{video_info['filename']}"
                                
                                if os.path.exists(video_path):
                                    print(f"📹 Found video: {video_info['filename']}")
                                    with open(video_path, "rb") as f:
                                        video_base64 = base64.b64encode(f.read()).decode()
                                    
                                    # Parse resolution from filename or settings
                                    resolution = settings.get('resolution', 'Unknown')
                                    
                                    # Clean up input directory after successful generation
                                    try:
                                        shutil.rmtree(input_dir)
                                        print("🧹 Cleaned up input directory after successful generation")
                                    except:
                                        pass  # Not critical if cleanup fails
                                    
                                    return {
                                        "success": True,
                                        "video_base64": video_base64,
                                        "filename": video_info['filename'],
                                        "resolution": resolution,
                                        "duration": elapsed,
                                        "debug": debug_info
                                    }
                                else:
                                    print(f"❌ Video file missing: {video_path}")
                        
                        # List all files in output directory for debugging
                        try:
                            output_files = os.listdir("/ComfyUI/output/")
                            print(f"📁 Files in /ComfyUI/output/: {output_files}")
                            
                            # Also check subdirectories (VHS might create subdirs)
                            for item in output_files:
                                item_path = f"/ComfyUI/output/{item}"
                                if os.path.isdir(item_path):
                                    subdir_files = os.listdir(item_path)
                                    print(f"📁 Files in /ComfyUI/output/{item}/: {subdir_files}")
                        except Exception as e:
                            print(f"❌ Could not list output directory: {e}")
                            
                        # Also check if output directory exists and permissions
                        print(f"📁 Output dir exists: {os.path.exists('/ComfyUI/output')}")
                        print(f"📁 Output dir writable: {os.access('/ComfyUI/output', os.W_OK)}")
                        
                        # Fallback: search for any video files in output directory
                        print("🔍 Searching for video files in /ComfyUI/output/...")
                        video_extensions = ['*.mp4', '*.avi', '*.mov', '*.mkv', '*.webm']
                        all_found_files = []
                        for ext in video_extensions:
                            found_files = glob.glob(f"/ComfyUI/output/{ext}")
                            if found_files:
                                all_found_files.extend(found_files)
                                print(f"  Found {len(found_files)} {ext} files")
                        
                        # Also check with prefix
                        prefix_search = glob.glob(f"/ComfyUI/output/runpod_video*")
                        if prefix_search:
                            all_found_files.extend(prefix_search)
                            print(f"  Found {len(prefix_search)} files with runpod_video prefix")
                        
                        # Search recursively in case VHS creates subdirectories
                        for ext in video_extensions:
                            recursive_search = glob.glob(f"/ComfyUI/output/**/{ext}", recursive=True)
                            if recursive_search:
                                all_found_files.extend(recursive_search)
                                print(f"  Found {len(recursive_search)} {ext} files recursively")
                        
                        if all_found_files:
                            # Use the most recent file
                            newest_file = max(all_found_files, key=os.path.getmtime)
                            print(f"📹 Found fallback video: {newest_file}")
                            
                            with open(newest_file, "rb") as f:
                                video_base64 = base64.b64encode(f.read()).decode()
                            
                            return {
                                "success": True,
                                "video_base64": video_base64,
                                "filename": os.path.basename(newest_file),
                                "resolution": settings.get('resolution', 'Unknown'),
                                "duration": elapsed,
                                "debug": debug_info
                            }
                        
                        # No video found despite completion
                        return {
                            "error": "Video generation completed but no output file found",
                            "debug": {**debug_info, "outputs": outputs}
                        }
                        
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Error checking job status: {e}")
            
            # Check queue status for progress indication
            try:
                queue_response = requests.get("http://localhost:8188/queue", timeout=5)
                if queue_response.ok:
                    queue_data = queue_response.json()
                    running = queue_data.get("queue_running", [])
                    
                    # If job is still running, update progress tracking
                    if running:
                        last_progress_time = time.time()
                        print(f"⏳ [{elapsed}s] Job still processing...")
                    elif time.time() - last_progress_time > 60:
                        # No progress for over 1 minute and not in running queue
                        return {
                            "error": "Job appears to be stuck or failed silently",
                            "debug": debug_info
                        }
            except:
                pass  # Queue check is not critical
            
            time.sleep(check_interval)
        
        return {
            "error": f"Video generation timed out after {max_wait_time} seconds",
            "debug": debug_info
        }
    
    except Exception as e:
        return {"error": f"Handler error: {str(e)}"}

# Initialize RunPod serverless
runpod.serverless.start({"handler": handler})