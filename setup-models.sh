#!/bin/bash

# Setup models from volume - downloads only if not cached
echo "🔧 Setting up models from volume..."

# Check if volume is mounted
if [ ! -d "/runpod-volume" ]; then
    echo "❌ Volume not mounted at /runpod-volume"
    exit 1
fi

# Create volume model directories
mkdir -p /runpod-volume/models/checkpoints
mkdir -p /runpod-volume/models/clip_vision  
mkdir -p /runpod-volume/models/vae

# Download models to volume if they don't exist
cd /runpod-volume

# WAN Model (13GB)
if [ ! -f "models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" ]; then
    echo "📥 Downloading WAN model to volume..."
    wget -c -O models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors \
        "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/v10/wan2.2-i2v-rapid-aio-v10.safetensors"
else
    echo "✅ WAN model already cached in volume"
fi

# CLIP Vision (1GB) 
if [ ! -f "models/clip_vision/clip_vision_vit_h.safetensors" ]; then
    echo "📥 Downloading CLIP model to volume..."
    wget -c -O models/clip_vision/clip_vision_vit_h.safetensors \
        "https://huggingface.co/lllyasviel/misc/resolve/main/clip_vision_vit_h.safetensors"
else
    echo "✅ CLIP model already cached in volume"
fi

# WAN VAE (334MB)
if [ ! -f "models/vae/wan2.2_vae.safetensors" ]; then
    echo "📥 Downloading WAN VAE to volume..."
    wget -c -O models/vae/wan2.2_vae.safetensors \
        "https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/resolve/main/vae/diffusion_pytorch_model.safetensors"
else
    echo "✅ WAN VAE already cached in volume"
fi

# Link volume models to ComfyUI
echo "🔗 Linking volume models to ComfyUI..."
ln -sf /runpod-volume/models/* /ComfyUI/models/

echo "🎉 Model setup complete!"