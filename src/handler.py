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
                "save_output": True
            },
            "class_type": "VHS_VideoCombine"
        }
    }
    
    return workflow

def handler(job):
    """RunPod serverless handler for Video Generator App"""
    try:
        print("🚀 YAY! Video Generator Handler starting! Version: 2025-01-07")
        print("🎉 HELLO! We're processing a new video generation job!")
        
        # Collect debug info to return in response
        debug_info = {"handler_version": "2025-01-07", "job_id": job.get("id", "unknown")}
        
        print(f"📋 YAY! Job details received: ID = {job.get('id', 'unknown')}")
        print(f"🔍 NICE! Job input structure: {list(job.get('input', {}).keys())}")
        
        # Validate required models (no volume, models downloaded in Docker build)
        required_models = {
            "wan_model": "/ComfyUI/models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors",
            # VAE is built into the checkpoint, no separate file needed
            "clip_vision": "/ComfyUI/models/clip_vision/clip_vision_vit_h.safetensors"
        }
        
        print("🔍 YAY! Let's check if our AI models are ready...")
        missing_models = []
        for model_name, model_path in required_models.items():
            if not os.path.exists(model_path):
                missing_models.append(f"{model_name} ({model_path})")
                debug_info[f"{model_name}_status"] = "NOT FOUND"
                print(f"❌ OH NO! Missing model: {model_path}")
            else:
                file_size = os.path.getsize(model_path)
                debug_info[f"{model_name}_status"] = f"OK ({file_size / (1024**3):.2f} GB)"
                print(f"✅ AWESOME! Found {model_name}: {model_path} ({file_size / (1024**3):.2f} GB)")
                print(f"🎉 GREAT! The {model_name} is ready and loaded!")
        
        if missing_models:
            print("💔 Oh no! Some models are missing. Can't generate videos without them!")
            return {
                "error": f"Missing required models: {', '.join(missing_models)}",
                "debug": debug_info
            }
        
        print("🎬 FANTASTIC! All AI models are loaded and ready to generate amazing videos!")
        
        # Start ComfyUI if not running
        print("🚀 EXCITING! Starting ComfyUI server...")
        if not start_comfyui():
            print("😭 OH NO! ComfyUI server failed to start!")
            return {"error": "Failed to start ComfyUI server", "debug": debug_info}
        print("🎉 WOOHOO! ComfyUI server is running and ready!")
        
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
        
        # Add VHS detection and debugging
        print("🔍 COOL! Let's check what nodes we have in our workflow...")
        for node_id, node_data in workflow.items():
            class_type = node_data.get("class_type", "Unknown")
            print(f"  📦 Node {node_id}: {class_type}")
            if class_type == "VHS_VideoCombine":
                print(f"  🎥 FOUND VHS_VideoCombine! Parameters: {list(node_data.get('inputs', {}).keys())}")
                vhs_inputs = node_data.get('inputs', {})
                print(f"    📹 filename_prefix: {vhs_inputs.get('filename_prefix', 'not set')}")
                print(f"    🎞️ format: {vhs_inputs.get('format', 'not set')}")
                print(f"    💾 save_output: {vhs_inputs.get('save_output', 'not set')}")
        
        # Queue workflow to ComfyUI
        print("🎬 AWESOME! Queuing video generation workflow to ComfyUI...")
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
                        print(f"✅ HOORAY! Job completed successfully! 🎉")
                        print(f"📊 NICE! Found outputs from {len(outputs)} nodes: {list(outputs.keys())}")
                        
                        # Debug: print all outputs to understand structure
                        print(f"🔍 COOL! Let's see what each node produced:")
                        for node_id, node_output in outputs.items():
                            print(f"  📦 Node {node_id}: {list(node_output.keys()) if isinstance(node_output, dict) else type(node_output)}")
                        
                        print(f"🔍 Full output structure (first 500 chars): {json.dumps(outputs, indent=2, default=str)[:500]}")
                        
                        # SIMPLIFIED VIDEO DETECTION: Just search for video files directly
                        # VHS_VideoCombine saves files but may not return them in outputs
                        print("🔍 EXCITING! Let's hunt for our generated video files...")
                        
                        # First, try to find video files by our prefix
                        video_found = False
                        video_path = None
                        
                        # Check for our prefixed files first
                        print("🎯 SEARCHING for files with 'runpod_video' prefix...")
                        prefix_files = glob.glob("/ComfyUI/output/runpod_video*")
                        if prefix_files:
                            video_path = max(prefix_files, key=os.path.getmtime)  # Get most recent
                            print(f"🎉 BINGO! Found our video with prefix: {video_path}")
                            print(f"📏 File size: {os.path.getsize(video_path) / 1024 / 1024:.2f} MB")
                            video_found = True
                        else:
                            print("🤔 Hmm, no files with 'runpod_video' prefix found...")
                        
                        # If no prefixed file, search for any video files
                        if not video_found:
                            print("🔍 Searching for any video files...")
                            video_extensions = ['*.mp4', '*.avi', '*.mov', '*.mkv', '*.webm']
                            all_found_files = []
                            
                            for ext in video_extensions:
                                found_files = glob.glob(f"/ComfyUI/output/{ext}")
                                if found_files:
                                    all_found_files.extend(found_files)
                                    print(f"  Found {len(found_files)} {ext} files")
                            
                            # Search recursively in case VHS creates subdirectories
                            for ext in video_extensions:
                                recursive_search = glob.glob(f"/ComfyUI/output/**/{ext}", recursive=True)
                                if recursive_search:
                                    all_found_files.extend(recursive_search)
                                    print(f"  Found {len(recursive_search)} {ext} files recursively")
                            
                            if all_found_files:
                                video_path = max(all_found_files, key=os.path.getmtime)  # Most recent
                                print(f"✅ Found fallback video: {video_path}")
                                video_found = True
                        
                        # If we found a video file, return it
                        if video_found and video_path and os.path.exists(video_path):
                            print(f"📹 Processing video: {video_path}")
                            
                            with open(video_path, "rb") as f:
                                video_base64 = base64.b64encode(f.read()).decode()
                            
                            # Clean up input directory after successful generation
                            try:
                                shutil.rmtree(input_dir)
                                print("🧹 Cleaned up input directory after successful generation")
                            except:
                                pass  # Not critical if cleanup fails
                            
                            return {
                                "success": True,
                                "video_base64": video_base64,
                                "filename": os.path.basename(video_path),
                                "resolution": settings.get('resolution', 'Unknown'),
                                "duration": elapsed,
                                "debug": debug_info
                            }
                        
                        # Debug: List all files for troubleshooting
                        try:
                            output_files = os.listdir("/ComfyUI/output/")
                            print(f"📁 DEBUG - All files in /ComfyUI/output/: {output_files}")
                        except Exception as e:
                            print(f"❌ Could not list output directory: {e}")
                        
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