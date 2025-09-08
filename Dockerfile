# SMART DOCKERFILE - Check first, install only if needed, fallbacks everywhere!
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

# Install system dependencies with smart checking
ENV DEBIAN_FRONTEND=noninteractive
RUN echo "🔍 Checking system packages..." && \
    # Check if packages are already installed
    if ! command -v python3 >/dev/null 2>&1 || ! command -v pip3 >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then \
        echo "📦 Installing missing system packages..." && \
        (apt-get clean && rm -rf /var/lib/apt/lists/* && apt-get update --fix-missing && \
         apt-get install -y --no-install-recommends --fix-broken \
         python3 python3-pip git wget curl ffmpeg libgl1-mesa-glx libglib2.0-0 ca-certificates && \
         apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/* || \
         echo "⚠️ Primary package install failed, trying alternative..." && \
         apt-get update && apt-get install -y python3 python3-pip git wget curl ffmpeg); \
    else \
        echo "✅ System packages already installed!"; \
    fi

# Set python3 as default (check first)
RUN if [ ! -L /usr/bin/python ]; then \
        ln -s /usr/bin/python3 /usr/bin/python && echo "🔗 Python symlink created"; \
    else \
        echo "✅ Python symlink already exists"; \
    fi

# Clone ComfyUI (check first)
WORKDIR /
RUN if [ ! -d "/ComfyUI" ]; then \
        echo "📥 Cloning ComfyUI..." && \
        (git clone https://github.com/comfyanonymous/ComfyUI.git || \
         echo "⚠️ Git clone failed, trying with depth 1..." && \
         git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git); \
    else \
        echo "✅ ComfyUI already exists"; \
    fi
WORKDIR /ComfyUI

# Install PyTorch (check first, CUDA 12.8 only with smart methods)
RUN echo "🔍 Checking PyTorch installation..." && \
    if ! python3 -c "import torch; print(f'Found PyTorch {torch.__version__}')" 2>/dev/null; then \
        echo "🔧 Installing PyTorch with CUDA 12.8 support..." && \
        (pip3 install --no-cache-dir --break-system-packages --upgrade --force-reinstall \
         torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
         --index-url https://download.pytorch.org/whl/cu128 || \
         echo "⚠️ Specific versions failed, trying latest CUDA 12.8 build..." && \
         pip3 install --no-cache-dir --break-system-packages \
         torch torchvision torchaudio \
         --index-url https://download.pytorch.org/whl/cu128 || \
         echo "⚠️ Index URL failed, trying direct install method..." && \
         pip3 install --no-cache-dir --break-system-packages --upgrade \
         torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu128) && \
        echo "✅ PyTorch installed successfully!"; \
    else \
        echo "✅ PyTorch already installed!"; \
    fi

# Install ComfyUI requirements (check first)
RUN if [ -f "requirements.txt" ]; then \
        echo "📦 Installing ComfyUI requirements..." && \
        (pip3 install --no-cache-dir --break-system-packages -r requirements.txt || \
         echo "⚠️ Requirements install failed, trying without break-system-packages..." && \
         pip3 install --no-cache-dir -r requirements.txt || \
         echo "⚠️ Continuing despite requirements failure...") && \
        echo "✅ ComfyUI requirements processed!"; \
    else \
        echo "⚠️ No requirements.txt found, skipping..."; \
    fi

# Create directories (check first)
RUN for dir in models/checkpoints models/clip_vision models/vae custom_nodes input output; do \
        if [ ! -d "$dir" ]; then \
            mkdir -p "$dir" && echo "📁 Created $dir"; \
        else \
            echo "✅ $dir already exists"; \
        fi; \
    done

# Install custom nodes (check first)
RUN cd custom_nodes && \
    # WanVideoWrapper
    if [ ! -d "ComfyUI-WanVideoWrapper" ]; then \
        echo "📦 Installing WanVideoWrapper..." && \
        (git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git || \
         echo "⚠️ Git clone failed for WanVideoWrapper") && \
        if [ -d "ComfyUI-WanVideoWrapper" ]; then \
            cd ComfyUI-WanVideoWrapper && \
            (pip3 install --no-cache-dir --break-system-packages -r requirements.txt || \
             pip3 install --no-cache-dir -r requirements.txt || \
             echo "⚠️ WanVideoWrapper requirements failed") && \
            cd ..; \
        fi; \
    else \
        echo "✅ WanVideoWrapper already installed"; \
    fi && \
    # VideoHelperSuite
    if [ ! -d "ComfyUI-VideoHelperSuite" ]; then \
        echo "📦 Installing VideoHelperSuite..." && \
        (git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git || \
         echo "⚠️ Git clone failed for VideoHelperSuite") && \
        if [ -d "ComfyUI-VideoHelperSuite" ]; then \
            cd ComfyUI-VideoHelperSuite && \
            (pip3 install --no-cache-dir --break-system-packages -r requirements.txt || \
             pip3 install --no-cache-dir -r requirements.txt || \
             echo "⚠️ VideoHelperSuite requirements failed") && \
            cd ..; \
        fi; \
    else \
        echo "✅ VideoHelperSuite already installed"; \
    fi && \
    echo "✅ Custom nodes processed!"

# Install additional dependencies (check first)
RUN echo "🔍 Checking additional dependencies..." && \
    missing_deps="" && \
    for pkg in runpod requests pillow opencv-python-headless; do \
        if ! python3 -c "import ${pkg//-/_}" 2>/dev/null; then \
            missing_deps="$missing_deps $pkg"; \
        fi; \
    done && \
    if [ -n "$missing_deps" ]; then \
        echo "📦 Installing missing dependencies:$missing_deps" && \
        (pip3 install --no-cache-dir --break-system-packages $missing_deps || \
         pip3 install --no-cache-dir $missing_deps || \
         echo "⚠️ Some dependencies failed to install"); \
    else \
        echo "✅ All dependencies already installed!"; \
    fi

# Install Hugging Face (check first)
RUN if ! python3 -c "import huggingface_hub" 2>/dev/null; then \
        echo "📦 Installing Hugging Face with fast transfer..." && \
        (pip3 install --no-cache-dir --break-system-packages "huggingface_hub[hf_transfer]" || \
         pip3 install --no-cache-dir "huggingface_hub[hf_transfer]" || \
         pip3 install --no-cache-dir huggingface_hub); \
    else \
        echo "✅ Hugging Face already installed!"; \
    fi

# Set environment for fast downloads
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# HF token passed as build argument
ARG HF_TOKEN
ENV HF_TOKEN=$HF_TOKEN

# Download WAN model (CHECK FIRST!)
RUN cd models/checkpoints && \
    if [ -f "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" ]; then \
        existing_size=$(stat -c%s "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" 2>/dev/null || echo "0") && \
        if [ "$existing_size" -gt 20000000000 ]; then \
            echo "✅ WAN model already exists and is valid ($(echo $existing_size | awk '{print $1/1024/1024/1024}') GB)!"; \
        else \
            echo "⚠️ WAN model exists but is corrupted, re-downloading..."; \
            rm -f "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors"; \
        fi; \
    fi && \
    if [ ! -f "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" ]; then \
        echo "🚀 Downloading WAN 2.2 model (24GB) with FAST transfer..." && \
        (hf download Phr00t/WAN2.2-14B-Rapid-AllInOne v10/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors || \
         echo "⚠️ Fast download failed, trying wget fallback..." && \
         wget --retry-connrefused --waitretry=5 --read-timeout=20 --timeout=15 -t 3 \
         -O wan2.2-i2v-rapid-aio-v10-nsfw.safetensors \
         "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" || \
         echo "❌ All download methods failed for WAN model") && \
        # Verify the download
        if [ -f "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" ]; then \
            python3 -c "import os; size = os.path.getsize('wan2.2-i2v-rapid-aio-v10-nsfw.safetensors'); print(f'✅ WAN model size: {size/1024/1024/1024:.2f} GB'); exit(1 if size < 20000000000 else 0)" && \
            echo "✅ WAN model verified!"; \
        fi; \
    fi

# Download CLIP Vision model (CHECK FIRST!)
RUN cd models/clip_vision && \
    if [ -f "clip_vision_vit_h.safetensors" ]; then \
        existing_size=$(stat -c%s "clip_vision_vit_h.safetensors" 2>/dev/null || echo "0") && \
        if [ "$existing_size" -gt 1000000000 ]; then \
            echo "✅ CLIP model already exists and is valid ($(echo $existing_size | awk '{print $1/1024/1024/1024}') GB)!"; \
        else \
            echo "⚠️ CLIP model exists but is corrupted, re-downloading..."; \
            rm -f "clip_vision_vit_h.safetensors"; \
        fi; \
    fi && \
    if [ ! -f "clip_vision_vit_h.safetensors" ]; then \
        echo "🚀 Downloading CLIP Vision model with FAST transfer..." && \
        (hf download lllyasviel/misc clip_vision_vit_h.safetensors || \
         echo "⚠️ Fast download failed, trying wget fallback..." && \
         wget -O clip_vision_vit_h.safetensors \
         "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors" || \
         echo "❌ All download methods failed for CLIP model") && \
        # Verify
        if [ -f "clip_vision_vit_h.safetensors" ]; then \
            python3 -c "import os; size = os.path.getsize('clip_vision_vit_h.safetensors'); print(f'✅ CLIP model size: {size/1024/1024/1024:.2f} GB'); exit(1 if size < 1000000000 else 0)" && \
            echo "✅ CLIP Vision model verified!"; \
        fi; \
    fi

# Copy our handler
COPY src/handler.py /handler.py

# Start handler
CMD ["python3", "/handler.py"]