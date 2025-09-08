# FRESH START - Complete pre-baked image with everything included
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

# Install system dependencies with retry and better error handling
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends --fix-broken \
    python3 \
    python3-pip \
    git \
    wget \
    curl \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ca-certificates \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set python3 as default
RUN ln -s /usr/bin/python3 /usr/bin/python

# Clone and setup ComfyUI fresh
WORKDIR /
RUN git clone https://github.com/comfyanonymous/ComfyUI.git
WORKDIR /ComfyUI

# Install PyTorch with CUDA 12.8 support (compatible with CUDA 12.8)
RUN echo "🔧 Installing PyTorch with CUDA support..." && \
    pip3 install --no-cache-dir --break-system-packages \
    torch==2.7.1 \
    torchvision==0.22.1 \
    torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/cu128 && \
    echo "✅ PyTorch installed successfully!"

# Install ComfyUI requirements
RUN echo "📦 Installing ComfyUI requirements..." && \
    pip3 install --no-cache-dir --break-system-packages -r requirements.txt && \
    echo "✅ ComfyUI requirements installed!"

# Create necessary directories
RUN mkdir -p models/checkpoints models/clip_vision models/vae custom_nodes input output

# Install custom nodes
RUN cd custom_nodes && \
    echo "📦 Installing WanVideoWrapper..." && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && \
    pip3 install --no-cache-dir --break-system-packages -r requirements.txt && \
    cd .. && \
    echo "📦 Installing VideoHelperSuite..." && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && \
    pip3 install --no-cache-dir --break-system-packages -r requirements.txt && \
    echo "✅ Custom nodes installed!"

# Install RunPod and additional dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    runpod \
    requests \
    pillow \
    opencv-python-headless

# Install Hugging Face with fast transfer
RUN pip3 install --no-cache-dir --break-system-packages "huggingface_hub[hf_transfer]"

# Set environment for fast downloads
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# HF token passed as build argument (RunPod will provide this)
ARG HF_TOKEN
ENV HF_TOKEN=$HF_TOKEN

# Download WAN model with FAST transfer + fallback (CORRECT REPO!)
RUN cd models/checkpoints && \
    echo "🚀 Downloading WAN 2.2 model (24GB) with FAST transfer..." && \
    (hf download Phr00t/WAN2.2-14B-Rapid-AllInOne v10/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors || \
    echo "⚠️ Fast download failed, trying wget fallback..." && \
    wget --retry-connrefused --waitretry=5 --read-timeout=20 --timeout=15 -t 3 \
    -O wan2.2-i2v-rapid-aio-v10-nsfw.safetensors \
    "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors") && \
    # Verify the download
    python3 -c "import os; size = os.path.getsize('wan2.2-i2v-rapid-aio-v10-nsfw.safetensors'); \
    print(f'✅ WAN model size: {size/1024/1024/1024:.2f} GB'); \
    if size < 20000000000: raise Exception('❌ Model file too small! Download failed!')" && \
    echo "✅ WAN model verified!"

RUN cd models/clip_vision && \
    echo "🚀 Downloading CLIP Vision model with FAST transfer..." && \
    hf download lllyasviel/misc clip_vision_vit_h.safetensors && \
    # Verify
    python3 -c "import os; size = os.path.getsize('clip_vision_vit_h.safetensors'); \
    print(f'✅ CLIP model size: {size/1024/1024/1024:.2f} GB'); \
    if size < 1000000000: raise Exception('❌ CLIP model too small!')" && \
    echo "✅ CLIP Vision model verified!"

# Copy our handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python3", "/handler.py"]