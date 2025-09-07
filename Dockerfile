# Simple and reliable build
FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python and essential packages
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    wget \
    curl \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set python3 as default python
RUN ln -s /usr/bin/python3 /usr/bin/python

# Install PyTorch CPU for build
RUN pip3 install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

WORKDIR /ComfyUI

# Everything in one mega layer for speed
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    git checkout f6b93d41 && \
    pip3 install --no-cache-dir -r requirements.txt runpod requests pillow opencv-python-headless && \
    mkdir -p models/checkpoints models/clip_vision custom_nodes input output && \
    cd custom_nodes && \
    git clone https://github.com/wan-h/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && git checkout 0ad24cd && pip3 install --no-cache-dir -r requirements.txt && \
    cd .. && git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && pip3 install --no-cache-dir -r requirements.txt && \
    cd /ComfyUI && \
    wget -q -O models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10.safetensors" && \
    wget -q -O models/clip_vision/clip_vision_vit_h.safetensors "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors"

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]