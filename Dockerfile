# RunPod GitHub Integration Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    curl \
    build-essential \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /ComfyUI

# Clone ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    pip install -r requirements.txt

# Create directories
RUN mkdir -p models/checkpoints models/clip_vision custom_nodes input output

# Install custom nodes for WAN
RUN cd custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git && \
    git clone https://github.com/kijai/ComfyUI-WAN2_I2V_nodes.git

# Install node requirements
RUN cd custom_nodes/ComfyUI-VideoHelperSuite && pip install -r requirements.txt || true
RUN cd custom_nodes/ComfyUI-AnimateDiff-Evolved && pip install -r requirements.txt || true
RUN cd custom_nodes/ComfyUI-WAN2_I2V_nodes && pip install -r requirements.txt || true

# Download models during build (avoid GitHub file size limits)
RUN wget -O /ComfyUI/models/checkpoints/wan2.2-i2v-rapid-aio-v10.safetensors "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10.safetensors"
RUN wget -O /ComfyUI/models/clip_vision/clip_vision_vit_h.safetensors "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors"

# Install handler dependencies
RUN pip install runpod requests pillow opencv-python

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]