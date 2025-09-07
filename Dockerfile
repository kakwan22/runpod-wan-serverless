# CUDA 12.1 as requested - RunPod 2025
FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04

# Install system dependencies with retry logic
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
    wget \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set python3 as default and upgrade pip
RUN ln -s /usr/bin/python3 /usr/bin/python && \
    python3 -m pip install --upgrade pip setuptools wheel

WORKDIR /ComfyUI

# Clone ComfyUI at specific version
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    git checkout f6b93d41

# Install ComfyUI requirements
RUN pip install --no-cache-dir -r requirements.txt

# Create local model directories and setup volume links
RUN mkdir -p models/checkpoints models/clip_vision models/vae custom_nodes input output

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

# Copy setup script for volume models
COPY setup-models.sh /setup-models.sh
RUN chmod +x /setup-models.sh

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]