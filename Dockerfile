# COMBINED DOCKERFILE - Uses Network Storage for Models
FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

# Install additional system packages we need
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    git wget curl ffmpeg \
    libgl1-mesa-glx libglib2.0-0 ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# Clone ComfyUI
WORKDIR /
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
WORKDIR /ComfyUI

# Install ComfyUI requirements
RUN pip3 install --no-cache-dir -r requirements.txt

# Create directories (network storage will mount over models/)
RUN mkdir -p models/checkpoints models/clip_vision models/vae custom_nodes input output

# Install custom nodes
WORKDIR /ComfyUI/custom_nodes
RUN git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && pip3 install --no-cache-dir -r requirements.txt
RUN git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && pip3 install --no-cache-dir -r requirements.txt

WORKDIR /ComfyUI

# Install additional dependencies
RUN pip3 install --no-cache-dir runpod requests pillow opencv-python-headless

# Install Hugging Face with fast transfer
RUN pip3 install --no-cache-dir "huggingface_hub[hf_transfer]"

# Set environment for fast downloads
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# CUDA optimizations for better performance
ENV PYTORCH_CUDA_ALLOC_CONF=backend:cudaMallocAsync

# HF token (not needed anymore but keeping for compatibility)
ARG HF_TOKEN
ENV HF_TOKEN=$HF_TOKEN

# Copy handler
COPY src/handler.py /handler.py

# Cleanup to reduce size
RUN rm -rf /root/.cache/pip/* && \
    find /usr -name "*.pyc" -delete && \
    find /usr -name "__pycache__" -delete && \
    rm -rf /tmp/*

# Start handler
CMD ["python3", "/handler.py"]