# CUDA 12.8 to match local setup - Ubuntu 24.04 LTS
FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu24.04

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
    curl \
    ca-certificates \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set python3 as default - skip upgrading system packages to avoid conflicts
RUN ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /ComfyUI

# Clone ComfyUI at specific version
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    git checkout f6b93d41

# Install ComfyUI requirements
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Create local model directories and setup volume links
RUN mkdir -p models/checkpoints models/clip_vision models/vae custom_nodes input output

# Install WanVideoWrapper - using kijai's repo (more stable)
RUN cd custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && \
    pip install --no-cache-dir --break-system-packages -r requirements.txt

# Install VideoHelperSuite version 1.7.4 (to match local)
RUN cd custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && \
    git checkout v1.7.4 || echo "v1.7.4 tag not found, using latest" && \
    pip install --no-cache-dir --break-system-packages -r requirements.txt
    
# Verify VideoHelperSuite installation and VHS nodes
RUN cd custom_nodes/ComfyUI-VideoHelperSuite && \
    echo "VideoHelperSuite version check:" && \
    python -c "print('VideoHelperSuite installed successfully')" && \
    ls -la *.py | head -5 && \
    echo "Checking for VHS_VideoCombine node:" && \
    grep -r "VHS_VideoCombine" . || echo "VHS_VideoCombine not found in text search" && \
    echo "Available node files:" && \
    find . -name "*.py" -exec grep -l "class.*Node" {} \;

# Install additional dependencies for RunPod
RUN pip install --no-cache-dir --break-system-packages \
    runpod \
    requests \
    pillow \
    opencv-python

# Download models using curl (more reliable than wget for HuggingFace)
RUN cd models/checkpoints && \
    echo "🔽 Downloading WAN model..." && \
    curl -L --progress-bar -o wan2.2-i2v-rapid-aio-v10-nsfw.safetensors \
    "https://huggingface.co/Kijai/WAN2.2/resolve/main/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" && \
    echo "✅ Downloaded WAN model ($(du -h wan2.2-i2v-rapid-aio-v10-nsfw.safetensors | cut -f1))" && \
    cd ../vae && \
    echo "🔽 Downloading VAE model..." && \
    curl -L --progress-bar -o wan2.2_vae.safetensors \
    "https://huggingface.co/Kijai/WAN2.2/resolve/main/wan2.2_vae.safetensors" && \
    echo "✅ Downloaded VAE model ($(du -h wan2.2_vae.safetensors | cut -f1))" && \
    cd ../clip_vision && \
    echo "🔽 Downloading CLIP Vision model..." && \
    curl -L --progress-bar -o clip_vision_vit_h.safetensors \
    "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors" && \
    echo "✅ Downloaded CLIP model ($(du -h clip_vision_vit_h.safetensors | cut -f1))"

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]