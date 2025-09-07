#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI Wan2.2 Video Generation Script
Uses ComfyUI API for real AI video generation with GGUF models
"""

import os
import sys
import json
import base64
import io
import time
import requests
from pathlib import Path
import subprocess
import signal
from PIL import Image

def kill_stuck_comfyui_processes():
    """Kill any stuck ComfyUI processes and free memory"""
    try:
        import psutil
        import gc
        killed_any = False
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
            try:
                # Check if it's a ComfyUI python process
                if proc.info['name'] == 'python.exe' and proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if 'main.py' in cmdline and 'ComfyUI' in cmdline:
                        memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                        print(f"🔥 Killing stuck ComfyUI process (PID: {proc.info['pid']}, Memory: {memory_mb:.0f}MB)", file=sys.stderr)
                        proc.kill()
                        killed_any = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        if killed_any:
            time.sleep(2)  # Give processes time to die
            gc.collect()  # Force garbage collection
            
    except ImportError:
        # Fallback to taskkill on Windows if psutil not available
        try:
            subprocess.run(['taskkill', '/F', '/IM', 'python.exe'], 
                         capture_output=True, check=False)
            print("🔥 Attempted to kill python processes via taskkill", file=sys.stderr)
        except:
            print("⚠️ Could not kill stuck processes - install psutil for better process management", file=sys.stderr)

def start_comfyui_server():
    """Check if ComfyUI server is running, start if needed"""
    try:
        # Check if ComfyUI is already running
        response = requests.get("http://localhost:8188", timeout=3)
        print("✅ ComfyUI server is already running", file=sys.stderr)
        return None
    except requests.exceptions.RequestException:
        print("🚀 ComfyUI server not detected, trying to start...", file=sys.stderr)
        
        # Only kill stuck processes if we can't connect after a few tries
        for attempt in range(2):
            try:
                response = requests.get("http://localhost:8188", timeout=2)
                break
            except:
                if attempt == 1:  # Last attempt failed
                    print("🔄 Cleaning up stuck processes before restart...", file=sys.stderr)
                    kill_stuck_comfyui_processes()
                time.sleep(1)
        
        # Check if ComfyUI path exists
        comfyui_path = Path("C:/Users/Kak/Desktop/ComfyUI")
        if not comfyui_path.exists():
            print("❌ ComfyUI not found. Please start ComfyUI manually first.", file=sys.stderr)
            raise FileNotFoundError("ComfyUI not found at expected location")
        
        # Start server with optimized flags
        print("🚀 Starting ComfyUI server with optimized settings...", file=sys.stderr)
        process = subprocess.Popen([
            sys.executable, "main.py", "--listen", "--disable-xformers", "--force-fp16"
        ], 
        cwd=str(comfyui_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        # Wait for server to start (longer timeout for slower systems)
        for i in range(20):  # Wait up to 20 seconds
            try:
                response = requests.get("http://localhost:8188", timeout=1)
                print("✅ ComfyUI server started successfully", file=sys.stderr)
                return process
            except requests.exceptions.RequestException:
                time.sleep(1)
                print(f"⏳ Starting ComfyUI server... ({i+1}/20)", file=sys.stderr)
        
        print("❌ ComfyUI server startup timeout. Please check your installation.", file=sys.stderr)
        raise RuntimeError("ComfyUI server failed to start within 20 seconds")

def calculate_auto_resolution(image_base64):
    """Calculate optimal resolution based on input image dimensions"""
    try:
        # Remove data URL prefix if present
        if image_base64.startswith('data:image'):
            image_base64 = image_base64.split(',')[1]
        
        # Decode image to get dimensions
        image_data = base64.b64decode(image_base64)
        
        image = Image.open(io.BytesIO(image_data))
        input_width, input_height = image.size
        
        print(f"📐 Input image dimensions: {input_width}x{input_height}", file=sys.stderr)
        
        # WAN 2.2 model works best with these resolutions, choose closest
        supported_resolutions = [
            (512, 512),
            (640, 640), 
            (768, 768),
            (1024, 1024),
            (512, 768),
            (768, 512),
            (640, 960),
            (960, 640),
            (1024, 768),
            (768, 1024)
        ]
        
        # Find closest resolution by aspect ratio and size
        input_aspect = input_width / input_height
        best_match = None
        best_score = float('inf')
        
        for width, height in supported_resolutions:
            aspect = width / height
            # Score based on aspect ratio difference and size difference
            aspect_diff = abs(aspect - input_aspect)
            size_diff = abs((width * height) - (input_width * input_height)) / (input_width * input_height)
            score = aspect_diff * 2 + size_diff  # Weight aspect ratio more
            
            if score < best_score:
                best_score = score
                best_match = (width, height)
        
        print(f"🎯 Auto resolution selected: {best_match[0]}x{best_match[1]} (aspect: {best_match[0]/best_match[1]:.2f})", file=sys.stderr)
        return best_match
    
    except Exception as e:
        print(f"⚠️ Error calculating auto resolution: {e}, using default 640x640", file=sys.stderr)
        return (640, 640)

def check_comfyui_nodes():
    """Check what VAE nodes are available in ComfyUI"""
    try:
        response = requests.get("http://localhost:8188/object_info", timeout=5)
        if response.status_code == 200:
            nodes = response.json()
            available_vae_nodes = []
            if "VAEDecode" in nodes:
                available_vae_nodes.append("VAEDecode")
            if "VAEDecodeTiled" in nodes:
                available_vae_nodes.append("VAEDecodeTiled")
            return available_vae_nodes
    except:
        pass
    return ["VAEDecode"]  # Always available

def create_vae_decode_node(vae_method, num_frames):
    """Create VAE decode node using separate WAN VAE"""
    print(f"🎨 Note: Using WAN VAE (wan2.2_vae.safetensors) for matching local results", file=sys.stderr)
    
    return {
        "inputs": {
            "samples": ["9", 0],
            "vae": ["12", 0]
        },
        "class_type": "VAEDecode"
    }

def create_safe_filename(prompt, max_length=50):
    """Create a safe filename from prompt"""
    import re
    if not prompt.strip():
        return "no_prompt"
    # Remove special characters and limit length
    safe_name = re.sub(r'[<>:"/\\|?*]', '', prompt.strip())
    safe_name = re.sub(r'\s+', '_', safe_name)
    return safe_name[:max_length]

def create_wan2_workflow(image_base64, prompt="", negative_prompt="", num_frames=16, seed=42, resolution="720p", fps=8, cfg=1.0, vae_decode_method="auto", steps=4, sampler_name="sa_solver", scheduler="beta", denoise=1.0, shift=8.0, crf=19):
    """Create Wan2.2 I2V workflow with correct dimensions and models"""
    
    # Save image to ComfyUI input folder first
    import uuid
    
    # Remove data URL prefix if present
    if image_base64.startswith('data:image'):
        image_base64 = image_base64.split(',')[1]
    
    # Decode and save image
    image_data = base64.b64decode(image_base64)
    image_filename = f"input_{uuid.uuid4().hex}.png"
    
    # Save to ComfyUI input folder
    comfyui_input = Path("C:/Users/Kak/Desktop/ComfyUI/input")
    comfyui_input.mkdir(exist_ok=True)
    
    image_path = comfyui_input / image_filename
    with open(image_path, 'wb') as f:
        f.write(image_data)
    
    print(f"📁 Saved input image: {image_path}", file=sys.stderr)
    
    # Determine dimensions based on resolution setting
    if resolution == "auto":
        width, height = calculate_auto_resolution(image_base64)
    elif resolution == "720p":
        width, height = 640, 640  # WAN 2.2 works better with square format
    elif resolution == "1080p":
        width, height = 1024, 1024  # Higher quality square format
    else:
        width, height = 640, 640  # Default fallback
    
    length = num_frames  # Use calculated frame count from duration and FPS
    
    # Create safe filename prefix from prompt
    safe_prompt = create_safe_filename(prompt)
    filename_prefix = f"{safe_prompt}_I2V"
    print(f"📝 Video filename prefix: {filename_prefix}", file=sys.stderr)
    
    # Determine VAE decode method
    if vae_decode_method == "auto":
        # Auto-select based on frame count
        if num_frames > 80:
            actual_vae_method = "tiled"
            print(f"🔧 Auto-selected Tiled VAE decode for {num_frames} frames (>80 frames)", file=sys.stderr)
        elif num_frames > 60:
            actual_vae_method = "tiled_overlap"
            print(f"🔧 Auto-selected Tiled-Overlap VAE decode for {num_frames} frames (60-80 frames)", file=sys.stderr)
        else:
            actual_vae_method = "standard"
            print(f"🔧 Using Standard VAE decode for {num_frames} frames (<60 frames)", file=sys.stderr)
    else:
        actual_vae_method = vae_decode_method
        print(f"🔧 Using {actual_vae_method} VAE decode method (user selected)", file=sys.stderr)
    
    print(f"🎬 Resolution: {width}x{height}, {num_frames} frames, FPS: {fps}, CFG: {cfg}", file=sys.stderr)
    
    workflow = {
        "1": {
            "inputs": {
                "image": image_filename,
                "upload": "image"
            },
            "class_type": "LoadImage"
        },
        "2": {
            "inputs": {
                "ckpt_name": "wan2.2-i2v-rapid-aio-v10.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "3": {
            "inputs": {
                "clip_name": "clip_vision_vit_h.safetensors"
            },
            "class_type": "CLIPVisionLoader"
        },
        "12": {
            "inputs": {
                "vae_name": "wan2.2_vae.safetensors"
            },
            "class_type": "VAELoader"
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
                "text": prompt or "",
                "clip": ["2", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "6": {
            "inputs": {
                "text": negative_prompt or "",
                "clip": ["2", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "shift": shift,
                "model": ["2", 0]
            },
            "class_type": "ModelSamplingSD3"
        },
        "8": {
            "inputs": {
                "positive": ["5", 0],
                "negative": ["6", 0],
                "vae": ["12", 0],
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
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
                "model": ["7", 0],
                "positive": ["8", 0],
                "negative": ["8", 1],
                "latent_image": ["8", 2]
            },
            "class_type": "KSampler"
        },
        "10": create_vae_decode_node(actual_vae_method, num_frames),
        "11": {
            "inputs": {
                "images": ["10", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": filename_prefix,
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": crf,
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            },
            "class_type": "VHS_VideoCombine"
        }
    }
    
    return workflow

def queue_workflow(workflow):
    """Queue workflow in ComfyUI"""
    try:
        response = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})
        
        if response.status_code != 200:
            print(f"❌ Failed to queue workflow: HTTP {response.status_code}", file=sys.stderr)
            try:
                error_details = response.json()
                print(f"❌ Error details: {error_details}", file=sys.stderr)
            except:
                print(f"❌ Response text: {response.text}", file=sys.stderr)
            return None
        
        result = response.json()
        prompt_id = result.get("prompt_id")
        
        if not prompt_id:
            print("❌ No prompt ID returned from ComfyUI", file=sys.stderr)
            print(f"❌ Response: {result}", file=sys.stderr)
            return None
        
        print(f"✅ Workflow queued successfully with ID: {prompt_id}", file=sys.stderr)
        return prompt_id
        
    except Exception as e:
        print(f"❌ Error queuing workflow: {e}", file=sys.stderr)
        return None

def wait_for_completion(prompt_id, expected_duration_seconds=240, update_interval=5):
    """Wait for workflow completion and get results with configurable updates"""
    start_time = time.time()
    last_progress_update = 0
    last_status = None
    stuck_at_95_time = None
    max_stuck_time = 180  # 3 minutes max stuck at 95%
    
    while True:
        try:
            # Check queue status
            response = requests.get("http://localhost:8188/queue", timeout=10)
            if response.status_code != 200:
                time.sleep(2)
                continue
                
            queue_data = response.json()
            elapsed = time.time() - start_time
            elapsed_int = int(elapsed)
            
            # Check if our prompt is still in queue
            running_items = queue_data.get("queue_running", [])
            pending_items = queue_data.get("queue_pending", [])
            running = any(item[1] == prompt_id for item in running_items)
            pending = any(item[1] == prompt_id for item in pending_items)
            
            # Get more detailed status from ComfyUI - but only log occasionally to reduce spam
            if running and len(running_items) > 0 and elapsed_int % 10 == 0:
                # Try to get current node being executed
                try:
                    # Try different endpoints to get execution info
                    history_response = requests.get(f"http://localhost:8188/history/{prompt_id}", timeout=2)
                    if history_response.status_code == 200:
                        history_data = history_response.json()
                        if prompt_id in history_data:
                            outputs = history_data[prompt_id].get('outputs', {})
                            # Log which nodes have completed
                            completed_nodes = list(outputs.keys())
                            if completed_nodes:
                                print(f"🔍 DEBUG: Completed nodes: {completed_nodes}", file=sys.stderr)
                            
                            # Infer current node based on what's completed
                            if '9' in completed_nodes:
                                print(f"📊 Stage: VAEDecode (node 10) - This is the slow part!", file=sys.stderr)
                            elif '10' in completed_nodes:
                                print(f"📊 Stage: VideoCombine (node 11) - Encoding video", file=sys.stderr)
                            else:
                                print(f"📊 Stage: KSampler (node 9) - Generating frames", file=sys.stderr)
                except Exception as e:
                    if elapsed_int % 30 == 0:  # Only log errors occasionally
                        print(f"🔍 DEBUG: Could not get node status: {e}", file=sys.stderr)
            
            # Track status changes for immediate updates
            current_status = 'running' if running else ('pending' if pending else 'processing')
            status_changed = current_status != last_status
            last_status = current_status
            
            if not running and not pending:
                # Check history for errors
                try:
                    history_response = requests.get(f"http://localhost:8188/history/{prompt_id}")
                    if history_response.status_code == 200:
                        history_data = history_response.json()
                        if prompt_id in history_data:
                            status = history_data[prompt_id].get('status', {})
                            if 'status_str' in status and status['status_str'] == 'error':
                                print(f"❌ Workflow failed with error", file=sys.stderr)
                                return None
                except:
                    pass
                
                # Check for output files
                time.sleep(2)
                output_files = get_output_files()
                
                if output_files:
                    print("✅ Video generation completed", file=sys.stderr)
                    return output_files
                else:
                    # If no output and not in queue for over 1 minute, probably failed
                    if elapsed > 60:
                        print("❌ Generation failed - no output files found", file=sys.stderr)
                        return None
            
            # More frequent and accurate progress updates
            if status_changed or (elapsed_int - last_progress_update >= update_interval):
                # Calculate more realistic progress based on expected duration
                if running:
                    # Progress estimation based on typical node execution times
                    # KSampler (node 9): ~70% of time
                    # VAEDecode (node 10): ~25% of time (THIS IS WHERE IT GETS STUCK)
                    # VideoCombine (node 11): ~5% of time
                    base_progress = 22
                    progress_range = 73  # 95 - 22
                    time_ratio = min(1.0, elapsed / expected_duration_seconds)
                    progress = base_progress + int(progress_range * time_ratio)
                    
                    # Add stage info if we're at certain progress points
                    stage_info = ""
                    if progress < 70:
                        stage_info = " - Generating frames"
                    elif progress < 90:
                        stage_info = " - Decoding frames (VAE)"
                    else:
                        stage_info = " - Encoding video"
                    
                    print(f"🎬 Generating video... {progress}% ({elapsed_int//60}m {elapsed_int%60}s){stage_info}", file=sys.stderr)
                elif pending:
                    # Queue pending: 5-20%
                    queue_progress = min(20, 5 + int(elapsed * 0.5))
                    print(f"⏳ Waiting in queue... {queue_progress}% ({elapsed_int//60}m {elapsed_int%60}s)", file=sys.stderr)
                else:
                    # Processing/finalizing: 95-99%
                    process_progress = min(99, 95 + int((elapsed - expected_duration_seconds) * 0.1))
                    print(f"🔄 Processing... {process_progress}% ({elapsed_int//60}m {elapsed_int%60}s)", file=sys.stderr)
                last_progress_update = elapsed_int
            
            time.sleep(2)
            
        except requests.exceptions.RequestException:
            elapsed = int(time.time() - start_time)
            if elapsed > 30:
                print(f"❌ ComfyUI connection lost ({elapsed//60}m {elapsed%60}s)", file=sys.stderr)
                try:
                    start_comfyui_server()
                except:
                    pass
            time.sleep(10)
            
        except Exception as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            time.sleep(10)

def get_output_files():
    """Get generated video files from ComfyUI output"""
    try:
        output_dir = Path("C:/Users/Kak/Desktop/ComfyUI/output")
        video_dir = output_dir / "video"
        
        # Check video subdirectory first (where files actually are)
        for check_dir in [video_dir, output_dir]:
            if check_dir.exists():
                video_files = list(check_dir.glob("*_I2V_*.mp4"))
                if not video_files:
                    video_files = list(check_dir.glob("*.mp4"))
                if not video_files:
                    video_files = list(check_dir.glob("*.webm"))
                
                if video_files:
                    latest_file = max(video_files, key=os.path.getctime)
                    print(f"✅ Generated video: {latest_file}", file=sys.stderr)
                    return str(latest_file)
        
        print("❌ No output video files found", file=sys.stderr)
        return None
            
    except Exception as e:
        print(f"Error getting output files: {e}", file=sys.stderr)
        return None

def generate_comfyui_video(
    image_base64, prompt="", negative_prompt="",
    resolution="720p", duration=4.0, 
    fps=8, seed=None, timeout_minutes=60,
    update_interval=5, cfg=1.0, vae_decode_method="auto",
    steps=4, sampler_name="sa_solver", scheduler="beta", 
    denoise=1.0, shift=8.0, crf=19
):
    """Main video generation function using ComfyUI"""
    try:
        print("🎬 Starting ComfyUI video generation...", file=sys.stderr)
        
        # Start ComfyUI server
        server_process = start_comfyui_server()
        
        try:
            # Calculate number of frames
            num_frames = int(duration * fps)
            if seed is None or seed == -1:
                seed = int(time.time())
            
            print(f"🎯 Target: {resolution}, {duration}s, {num_frames} frames ({duration}s × {fps}fps), CFG: {cfg}, seed: {seed}", file=sys.stderr)
            
            # Warn about frame limits
            if num_frames > 60:
                print(f"⚠️ WARNING: {num_frames} frames may cause VAE decode to hang (>60 frames risky)", file=sys.stderr)
                print(f"⚠️ VAE decode time increases exponentially with frame count", file=sys.stderr)
                print(f"⚠️ Consider: Lower FPS ({fps}→{fps//2}) or shorter duration ({duration}s→{duration/2}s)", file=sys.stderr)
            elif num_frames > 48:
                print(f"⚡ Note: {num_frames} frames - VAE decode may be slow at final stage", file=sys.stderr)
            
            # User-configurable timeout
            timeout_seconds = timeout_minutes * 60
            
            print(f"⏰ Timeout set to {timeout_minutes} minutes for this generation", file=sys.stderr)
            
            # Create workflow with all advanced settings
            workflow = create_wan2_workflow(
                image_base64, prompt, negative_prompt, num_frames, seed, resolution, fps, 
                cfg, vae_decode_method, steps, sampler_name, scheduler, denoise, shift, crf
            )
            
            # Queue workflow
            prompt_id = queue_workflow(workflow)
            if not prompt_id:
                return {"success": False, "error": "Failed to queue ComfyUI workflow"}
            
            # Wait for completion with estimated duration (for progress calculation)
            # Estimate: ~1 minute per second of video + overhead
            expected_duration = max(60, duration * 60 + 30)
            video_path = wait_for_completion(prompt_id, expected_duration, update_interval)
            if not video_path:
                return {"success": False, "error": "Video generation failed or timed out"}
            
            # Convert to MP4 if needed and copy to our output directory
            output_dir = Path(__file__).parent.parent / "Output"
            output_dir.mkdir(exist_ok=True)
            
            # Create descriptive filename with prompt
            safe_prompt = create_safe_filename(prompt)
            final_path = output_dir / f"{safe_prompt}_{int(time.time())}.mp4"
            
            # Copy the file
            import shutil
            shutil.copy2(video_path, final_path)
            
            # Thumbnail generation removed - video already has embedded thumbnails
            
            result = {
                "success": True,
                "video_path": str(final_path),
                "duration": duration,
                "resolution": resolution,
                "frames": num_frames,
                "fps": fps,
                "comfyui_source": str(video_path)
            }
            
            # Always clean up the server to free memory
            if server_process and not server_process.poll():
                print("🔄 Stopping ComfyUI server to free memory...", file=sys.stderr)
                try:
                    server_process.terminate()
                    server_process.wait(timeout=5)
                    print("✅ ComfyUI server stopped", file=sys.stderr)
                except:
                    server_process.kill()
                    print("⚡ ComfyUI server force killed", file=sys.stderr)
            
            # Clean up any remaining ComfyUI processes to prevent memory leaks
            kill_stuck_comfyui_processes()
                    
            return result
            
        finally:
            # Cleanup on any error or exception
            if 'server_process' in locals() and server_process and not server_process.poll():
                try:
                    server_process.kill()
                    print("⚡ ComfyUI server killed due to error", file=sys.stderr)
                except:
                    pass
            
    except Exception as e:
        print(f"❌ Error in ComfyUI video generation: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        
        # Don't kill server on error either
            
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            result = {"success": False, "error": "Usage: python comfyui_video_generation.py <params_file>"}
        else:
            params_file = sys.argv[1]
            
            # Read parameters
            with open(params_file, 'r') as f:
                params = json.load(f)
            
            result = generate_comfyui_video(
                image_base64=params.get('inputImage', ''),
                prompt=params.get('prompt', ''),
                negative_prompt=params.get('negativePrompt', ''),
                resolution=params.get('resolution', '720p'),
                duration=params.get('duration', 4.0),
                fps=params.get('fps', 8),
                seed=params.get('seed', -1),
                timeout_minutes=params.get('timeoutMinutes', 60),
                update_interval=params.get('updateInterval', 5),
                cfg=params.get('cfg', 1.0),
                vae_decode_method=params.get('vaeDecodeMethod', 'auto'),
                steps=params.get('steps', 4),
                sampler_name=params.get('samplerName', 'sa_solver'),
                scheduler=params.get('scheduler', 'beta'),
                denoise=params.get('denoise', 1.0),
                shift=params.get('shift', 8.0),
                crf=params.get('crf', 19)
            )
        
        # Output JSON result
        json_output = json.dumps(result)
        sys.stdout.write(json_output + '\n')
        sys.stdout.flush()
        
    except Exception as e:
        error_result = {"success": False, "error": f"Unexpected error: {str(e)}"}
        json_output = json.dumps(error_result)
        sys.stdout.write(json_output + '\n')
        sys.stdout.flush()