# Ultra-fast minimal build
FROM python:3.11-slim

# Install system deps in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ffmpeg libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU (will work fine for ComfyUI setup, GPU handled by runtime)
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

WORKDIR /ComfyUI

# Everything in one mega layer for speed
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    git checkout f6b93d41 && \
    pip install --no-cache-dir -r requirements.txt runpod requests pillow opencv-python-headless && \
    mkdir -p models/checkpoints models/clip_vision custom_nodes input output && \
    cd custom_nodes && \
    git clone https://github.com/wan-h/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && git checkout 0ad24cd && pip install --no-cache-dir -r requirements.txt && \
    cd .. && git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && pip install --no-cache-dir -r requirements.txt && \
    cd /ComfyUI && \
    wget -q -O models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10.safetensors" && \
    wget -q -O models/clip_vision/clip_vision_vit_h.safetensors "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors"

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]