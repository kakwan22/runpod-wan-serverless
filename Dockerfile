# MINIMAL RUNPOD DOCKERFILE - PyTorch 2.7.1 + CUDA 12.8 
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

# Install system packages
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3 python3-pip git wget curl ffmpeg \
    libgl1-mesa-glx libglib2.0-0 ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# Set python3 as default
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Clone ComfyUI
WORKDIR /
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
WORKDIR /ComfyUI

# Install PyTorch 2.7.1 + CUDA 12.8
RUN pip3 install --no-cache-dir \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/cu128

# Install ComfyUI requirements
RUN pip3 install --no-cache-dir -r requirements.txt

# Create directories
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

# HF token
ARG HF_TOKEN
ENV HF_TOKEN=$HF_TOKEN

# Download WAN model (check first - 24GB)
RUN cd models/checkpoints && \
    if [ ! -f "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" ] || [ $(stat -c%s "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" 2>/dev/null || echo 0) -lt 20000000000 ]; then \
        echo "Downloading WAN 2.2 model..." && \
        hf download Phr00t/WAN2.2-14B-Rapid-AllInOne v10/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors; \
    fi

# Download CLIP Vision model (check first - 1.7GB)
RUN cd models/clip_vision && \
    if [ ! -f "clip_vision_vit_h.safetensors" ] || [ $(stat -c%s "clip_vision_vit_h.safetensors" 2>/dev/null || echo 0) -lt 1000000000 ]; then \
        echo "Downloading CLIP Vision model..." && \
        hf download lllyasviel/misc clip_vision_vit_h.safetensors; \
    fi

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python3", "/handler.py"]