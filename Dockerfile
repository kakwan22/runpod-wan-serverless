# RunPod GitHub Integration Dockerfile - Optimized build
FROM runpod/pytorch:2.2.0-py3.11-cuda12.1.1-devel-ubuntu22.04

# Install minimal dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /ComfyUI

# Clone and setup ComfyUI in one layer to avoid timeouts
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    git checkout f6b93d41 && \
    pip install --no-cache-dir -r requirements.txt && \
    mkdir -p models/checkpoints models/clip_vision custom_nodes input output && \
    cd custom_nodes && \
    git clone https://github.com/wan-h/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && \
    git checkout 0ad24cd && \
    pip install --no-cache-dir -r requirements.txt && \
    cd .. && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && \
    pip install --no-cache-dir -r requirements.txt

# Download models and install handler deps in one layer
RUN pip install --no-cache-dir runpod requests pillow opencv-python && \
    wget -q -O models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10.safetensors" && \
    wget -q -O models/clip_vision/clip_vision_vit_h.safetensors "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors"

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]