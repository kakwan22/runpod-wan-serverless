# RunPod GitHub Integration Dockerfile - Matched to local versions
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

# Install system dependencies and Python 3.12 (closest to your 3.13.7)
RUN apt-get update && apt-get install -y \
    software-properties-common \
    git \
    wget \
    curl \
    build-essential \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y python3.12 python3.12-venv python3.12-dev \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && rm -rf /var/lib/apt/lists/*

# Install pip
RUN curl https://bootstrap.pypa.io/get-pip.py | python

# Set working directory
WORKDIR /ComfyUI

# Clone ComfyUI at EXACT version 0.3.52 (commit f6b93d41)
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    git checkout f6b93d41 && \
    pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
    pip install -r requirements.txt

# Create directories
RUN mkdir -p models/checkpoints models/clip_vision custom_nodes input output

# Install EXACT version of WanVideoWrapper that you have (commit 0ad24cd)
RUN cd custom_nodes && \
    git clone https://github.com/wan-h/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && \
    git checkout 0ad24cd && \
    pip install -r requirements.txt

# Install VideoHelperSuite for video output
RUN cd custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && \
    pip install -r requirements.txt

# Download models during build (avoid GitHub file size limits)
RUN wget -O /ComfyUI/models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10.safetensors"
RUN wget -O /ComfyUI/models/clip_vision/clip_vision_vit_h.safetensors "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors"

# Install handler dependencies
RUN pip install runpod requests pillow opencv-python

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]