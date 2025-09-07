# ComfyUI Docker for RunPod - 2025
FROM python:3.11

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    curl \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ComfyUI

# Clone ComfyUI at specific version
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    git checkout f6b93d41

# Install ComfyUI requirements
RUN pip install --no-cache-dir -r requirements.txt

# Create model directories
RUN mkdir -p models/checkpoints models/clip_vision custom_nodes input output

# Install WanVideoWrapper - using kijai's repo (more stable)
RUN cd custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && \
    pip install --no-cache-dir -r requirements.txt

# Install VideoHelperSuite
RUN cd custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && \
    pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for RunPod
RUN pip install --no-cache-dir \
    runpod \
    requests \
    pillow \
    opencv-python

# Download required models
RUN wget -O models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors \
    "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10.safetensors"

RUN wget -O models/clip_vision/clip_vision_vit_h.safetensors \
    "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors"

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]