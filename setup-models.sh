#!/bin/bash

# Setup models from RunPod volume storage
echo "🔧 Setting up models from volume storage..."

# Volume mount point (RunPod standard)
VOLUME_PATH="/workspace"
COMFYUI_PATH="/ComfyUI"

# Function to copy or link model if it exists
copy_model() {
    local src="$1"
    local dest="$2"
    local name="$3"
    
    if [ -f "$src" ]; then
        echo "✅ Found $name at $src"
        echo "   📂 Copying to $dest"
        
        # Create destination directory if it doesn't exist
        mkdir -p "$(dirname "$dest")"
        
        # Copy the file (use cp instead of ln for RunPod compatibility)
        cp "$src" "$dest"
        
        if [ $? -eq 0 ]; then
            echo "   ✅ Successfully copied $name"
            echo "   📦 Size: $(du -h "$dest" | cut -f1)"
        else
            echo "   ❌ Failed to copy $name"
            return 1
        fi
    else
        echo "❌ $name not found at $src"
        echo "   🔍 Checking if directory exists: $(dirname "$src")"
        if [ -d "$(dirname "$src")" ]; then
            echo "   📁 Directory contents:"
            ls -la "$(dirname "$src")" | head -10
        else
            echo "   📁 Directory does not exist"
        fi
        return 1
    fi
}

# Check if volume is mounted
if [ ! -d "$VOLUME_PATH" ]; then
    echo "❌ Volume not mounted at $VOLUME_PATH"
    exit 1
fi

echo "📁 Volume contents:"
ls -la "$VOLUME_PATH" | head -10

# Check for models directory in volume
if [ -d "$VOLUME_PATH/models" ]; then
    echo "✅ Models directory found in volume"
    ls -la "$VOLUME_PATH/models"
else
    echo "❌ No models directory in volume"
    echo "📁 Available directories in volume:"
    find "$VOLUME_PATH" -maxdepth 2 -type d | head -20
fi

# Copy WAN 2.2 model
copy_model \
    "$VOLUME_PATH/models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" \
    "$COMFYUI_PATH/models/checkpoints/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors" \
    "WAN 2.2 Model"

# Copy WAN VAE
copy_model \
    "$VOLUME_PATH/models/vae/wan2.2_vae.safetensors" \
    "$COMFYUI_PATH/models/vae/wan2.2_vae.safetensors" \
    "WAN VAE"

# Copy CLIP Vision model
copy_model \
    "$VOLUME_PATH/models/clip_vision/clip_vision_vit_h.safetensors" \
    "$COMFYUI_PATH/models/clip_vision/clip_vision_vit_h.safetensors" \
    "CLIP Vision"

# Alternative paths to check (in case models are in different locations)
echo "🔍 Searching for models in volume..."

find "$VOLUME_PATH" -name "*.safetensors" -type f | head -10 | while read -r file; do
    echo "   📄 Found: $file ($(du -h "$file" | cut -f1))"
done

echo "🏁 Model setup complete!"