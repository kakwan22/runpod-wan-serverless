# Bulletproof minimal Dockerfile
FROM python:3.11

# Install git only (minimum needed)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /ComfyUI

# Clone ComfyUI and install requirements
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    git checkout f6b93d41 && \
    pip install -r requirements.txt

# Create directories  
RUN mkdir -p models/checkpoints models/clip_vision custom_nodes input output

# Install custom nodes
RUN cd custom_nodes && \
    git clone https://github.com/wan-h/ComfyUI-WanVideoWrapper.git && \
    cd ComfyUI-WanVideoWrapper && \
    git checkout 0ad24cd && \
    pip install -r requirements.txt

RUN cd custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && \
    pip install -r requirements.txt

# Install handler dependencies
RUN pip install runpod requests pillow opencv-python

# Download models
RUN wget -O models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10.safetensors"
RUN wget -O models/clip_vision/clip_vision_vit_h.safetensors "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors"

# Copy handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python", "/handler.py"]