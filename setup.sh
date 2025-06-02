#!/bin/bash

# Function to check if a command exists
command_exists () {
    command -v "$1" >/dev/null 2>&1
}

# Check for ffmpeg
if command_exists ffmpeg && command_exists ffprobe; then
    echo "ffmpeg and ffprobe found."
else
    echo "---------------------------------------------------------------------"
    echo "WARNING: ffmpeg or ffprobe not found in your system's PATH."
    echo "This application requires ffmpeg (and its component ffprobe) for:"
    echo "  1. Creating test audio clips for the Whisper speed test feature."
    echo "  2. Getting accurate audio durations for files."
    echo ""
    echo "Please install ffmpeg. Common installation methods:"
    echo "  - macOS (using Homebrew): brew install ffmpeg"
    echo "  - Debian/Ubuntu Linux: sudo apt update && sudo apt install ffmpeg"
    echo "  - Fedora Linux: sudo dnf install ffmpeg"
    echo "  - Windows: Download from https://ffmpeg.org/download.html and add to PATH."
    echo ""
    echo "After installation, please re-run this setup script or ensure"
    echo "ffmpeg and ffprobe are accessible from your terminal before running the app."
    echo "---------------------------------------------------------------------"
    # It's a warning, so we can continue with Python environment setup,
    # but the app's functionality will be limited without ffmpeg.
fi

echo ""
echo "Creating Python 3.11 virtual environment named 'venv'..."
python3.11 -m venv venv

echo "Activating virtual environment..."
# Note: Activation within this script only affects this script's execution.
# The user will need to activate it manually in their terminal session.
source venv/bin/activate

echo "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel

echo "Installing Flask and openai-whisper..."
pip install flask openai-whisper

echo ""
echo "---------------------------------------------------------------------"
echo "Setup complete!"
echo "Python packages have been installed into the 'venv' virtual environment."
echo ""
echo "IMPORTANT NEXT STEP:"
echo "To run the application, you first need to activate this virtual environment"
echo "in your terminal session. Open a new terminal or use your current one:"
echo ""
echo "  For macOS/Linux: source venv/bin/activate"
echo "  For Windows:     venv\Scripts\activate"
echo ""
echo "Then, you can run the server with: python3 app.py"
echo "---------------------------------------------------------------------"
