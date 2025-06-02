#!/bin/bash

# --- Configuration ---
PYTHON_VERSION_TARGET="3.11.4" # Target a specific patch version for pyenv
PYTHON_COMMAND_FALLBACK="python3.11" # Fallback command if pyenv is not used

# --- Helper Functions ---
command_exists () {
    command -v "$1" >/dev/null 2>&1
}

print_info () {
    echo "INFO: $1"
}

print_warning () {
    echo "---------------------------------------------------------------------"
    echo "WARNING: $1"
    echo "---------------------------------------------------------------------"
}

print_error_exit () {
    echo "---------------------------------------------------------------------"
    echo "ERROR: $1"
    echo "Exiting setup."
    echo "---------------------------------------------------------------------"
    exit 1
}

# --- Dependency Checks (ffmpeg) ---
echo "Checking for ffmpeg and ffprobe..."
if command_exists ffmpeg && command_exists ffprobe; then
    print_info "ffmpeg and ffprobe found."
else
    print_warning "ffmpeg or ffprobe not found in your system's PATH.
This application requires ffmpeg (and its component ffprobe) for:
  1. Creating test audio clips for the Whisper speed test feature.
  2. Getting accurate audio durations for files.

Please install ffmpeg. Common installation methods:
  - macOS (using Homebrew): brew install ffmpeg
  - Debian/Ubuntu Linux: sudo apt update && sudo apt install ffmpeg
  - Fedora Linux: sudo dnf install ffmpeg
  - Windows: Download from https://ffmpeg.org/download.html and add to PATH.

After installation, please re-run this setup script or ensure
ffmpeg and ffprobe are accessible from your terminal before running the app."
    # Continue, as some app functionality might still work, but warn user.
fi
echo ""


# --- Python Environment Setup ---
VENV_DIR="venv"
PYTHON_EXEC="python" # Default to 'python', will be versioned by pyenv or venv

echo "Setting up Python environment..."

if command_exists pyenv; then
    print_info "pyenv found. Attempting to set up Python $PYTHON_VERSION_TARGET using pyenv."

    # Ensure pyenv shims are in PATH (common setup step for pyenv)
    if [[ -z "$(pyenv root)/shims" || ":$PATH:" != *":$(pyenv root)/shims:"* ]]; then
         print_info "Consider adding 'eval "$(pyenv init -)"' to your shell profile (.bashrc, .zshrc, etc.) for pyenv shims if you haven't already."
    fi

    # Check if the target Python version is installed by pyenv
    if ! pyenv versions --bare | grep -q -x "$PYTHON_VERSION_TARGET"; then
        print_info "Python $PYTHON_VERSION_TARGET not found in pyenv. Attempting to install it..."
        if ! pyenv install "$PYTHON_VERSION_TARGET"; then
            print_error_exit "Failed to install Python $PYTHON_VERSION_TARGET using pyenv.
Please install it manually with 'pyenv install $PYTHON_VERSION_TARGET', ensure your pyenv setup is correct, then re-run this script."
        fi
        print_info "Python $PYTHON_VERSION_TARGET installed successfully via pyenv."
    else
        print_info "Python $PYTHON_VERSION_TARGET is already installed in pyenv."
    fi

    # Set local Python version for this project directory
    # This creates/updates .python-version
    if ! pyenv local "$PYTHON_VERSION_TARGET"; then
        print_error_exit "Failed to set Python $PYTHON_VERSION_TARGET as local version using 'pyenv local'. Please check your pyenv installation."
    fi
    print_info "Set local Python version to $PYTHON_VERSION_TARGET for this project (see .python-version file)."

    # Use the pyenv-provided python to create the virtual environment
    # 'python' command should now resolve to the pyenv-set version
    print_info "Creating virtual environment '$VENV_DIR' using pyenv's Python $PYTHON_VERSION_TARGET..."
    if ! python -m venv "$VENV_DIR"; then
        print_error_exit "Failed to create virtual environment using 'python -m venv $VENV_DIR'.
Ensure pyenv shims are active in your current shell or re-source your shell profile."
    fi
    PYTHON_EXEC="$VENV_DIR/bin/python" # Use the venv python for subsequent steps if pyenv was used.
else
    print_info "pyenv not found."
    print_info "Attempting to use system '$PYTHON_COMMAND_FALLBACK' to create virtual environment '$VENV_DIR'..."
    if command_exists "$PYTHON_COMMAND_FALLBACK"; then
        if ! "$PYTHON_COMMAND_FALLBACK" -m venv "$VENV_DIR"; then
            print_error_exit "Failed to create virtual environment using '$PYTHON_COMMAND_FALLBACK -m venv $VENV_DIR'.
Please check your Python $PYTHON_COMMAND_FALLBACK installation."
        fi
        PYTHON_EXEC="$VENV_DIR/bin/python"
    else
        print_error_exit "'$PYTHON_COMMAND_FALLBACK' command not found.
Please install Python $PYTHON_COMMAND_FALLBACK (matching $PYTHON_VERSION_TARGET if possible),
or install pyenv (https://github.com/pyenv/pyenv), install Python $PYTHON_VERSION_TARGET via pyenv, and then re-run this script."
    fi
fi

print_info "Virtual environment '$VENV_DIR' created successfully."
echo ""

print_info "Activating virtual environment for script execution..."
# Note: Activation within this script only affects this script's execution.
# The user will need to activate it manually in their terminal session later.
source "$VENV_DIR/bin/activate"

print_info "Upgrading pip, setuptools, and wheel using '$PYTHON_EXEC' from venv..."
# Use $PYTHON_EXEC -m pip to be absolutely sure we're using the venv's pip
"$PYTHON_EXEC" -m pip install --upgrade pip setuptools wheel

print_info "Installing Flask and openai-whisper using '$PYTHON_EXEC' from venv..."
"$PYTHON_EXEC" -m pip install flask openai-whisper

echo ""
echo "---------------------------------------------------------------------"
print_info "Setup complete!"
print_info "Python packages have been installed into the '$VENV_DIR' virtual environment."
echo ""
echo "IMPORTANT NEXT STEP:"
echo "To run the application, you first need to activate this virtual environment"
echo "in your terminal session. Open a new terminal or use your current one:"
echo ""
echo "  For macOS/Linux: source $VENV_DIR/bin/activate"
echo "  For Windows:     $VENV_DIR\Scripts\activate"
echo ""
echo "Then, you can run the server with: python app.py"
echo "---------------------------------------------------------------------"
