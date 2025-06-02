#!/bin/bash

# --- Configuration ---
PYTHON_VERSION_TARGET="3.11.4" # Target a specific patch version for pyenv
PYTHON_COMMAND_FALLBACK="python3.11" # Fallback command if pyenv is not used
VENV_DIR="venv"

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

attempt_pyenv_install_guidance() {
    echo "---------------------------------------------------------------------"
    read -r -p "pyenv not found, and system Python setup failed. Would you like to attempt to install pyenv using git? (This will clone it into ~/.pyenv) [y/N] " response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        if ! command_exists git; then
            print_error_exit "git is not installed. Please install git first, then re-run this script or install pyenv manually."
        fi
        print_info "Attempting to clone pyenv from GitHub into ~/.pyenv..."
        if git clone https://github.com/pyenv/pyenv.git ~/.pyenv; then
            echo "pyenv cloned successfully into ~/.pyenv."
            echo ""
            echo "IMPORTANT: To complete pyenv installation, you MUST configure your shell."
            echo "Please add the following lines to your shell configuration file (e.g., ~/.bashrc, ~/.zshrc, ~/.profile, or ~/.config/fish/config.fish):"
            echo ""
            echo '  export PYENV_ROOT="$HOME/.pyenv"'
            echo '  export PATH="$PYENV_ROOT/bin:$PATH"'
            echo '  eval "$(pyenv init --path)"'
            echo '  eval "$(pyenv init -)"' # For shims and autocompletion
            echo ""
            echo "After adding these lines, YOU MUST RESTART YOUR SHELL or source your shell configuration file (e.g., source ~/.bashrc)."
            echo "Once your shell is restarted and pyenv is configured, please RE-RUN THIS SETUP SCRIPT (./setup.sh)."
            exit 0 # Exit successfully to allow user to configure shell and re-run
        else
            print_error_exit "Failed to clone pyenv from GitHub. Please check your internet connection or install pyenv manually."
        fi
    else
        print_info "Skipping pyenv installation attempt."
    fi
    echo "---------------------------------------------------------------------"
}

# --- Dependency Checks (ffmpeg) ---
echo "Checking for ffmpeg and ffprobe..."
if command_exists ffmpeg && command_exists ffprobe; then
    print_info "ffmpeg and ffprobe found."
else
    print_warning "ffmpeg or ffprobe not found in your system's PATH.\nThis application requires ffmpeg (and its component ffprobe) for:\n  1. Creating test audio clips for the Whisper speed test feature.\n  2. Getting accurate audio durations for files.\n\nPlease install ffmpeg. Common installation methods:\n  - macOS (using Homebrew): brew install ffmpeg\n  - Debian/Ubuntu Linux: sudo apt update && sudo apt install ffmpeg\n  - Fedora Linux: sudo dnf install ffmpeg\n  - Windows: Download from https://ffmpeg.org/download.html and add to PATH.\n\nAfter installation, please re-run this setup script or ensure\nffmpeg and ffprobe are accessible from your terminal before running the app."
fi
echo ""

# --- Python Environment Setup ---
PYTHON_EXEC="python"

echo "Setting up Python environment..."

if command_exists pyenv; then
    print_info "pyenv found. Attempting to set up Python $PYTHON_VERSION_TARGET using pyenv."
    if [[ -z "$(pyenv root)/shims" || ":$PATH:" != *":$(pyenv root)/shims:"* ]]; then
         print_info "Consider adding 'eval \"$(pyenv init -)\"' to your shell profile for pyenv shims if you haven't already."
    fi
    if ! pyenv versions --bare | grep -q -x "$PYTHON_VERSION_TARGET"; then
        print_info "Python $PYTHON_VERSION_TARGET not found in pyenv. Attempting to install it..."
        if ! pyenv install "$PYTHON_VERSION_TARGET"; then
            print_error_exit "Failed to install Python $PYTHON_VERSION_TARGET using pyenv.\nPlease install it manually with 'pyenv install $PYTHON_VERSION_TARGET', ensure pyenv setup is correct, then re-run this script."
        fi
        print_info "Python $PYTHON_VERSION_TARGET installed successfully via pyenv."
    else
        print_info "Python $PYTHON_VERSION_TARGET is already installed in pyenv."
    fi
    if ! pyenv local "$PYTHON_VERSION_TARGET"; then
        print_error_exit "Failed to set Python $PYTHON_VERSION_TARGET as local version using 'pyenv local'."
    fi
    print_info "Set local Python version to $PYTHON_VERSION_TARGET for this project."
    print_info "Creating virtual environment '$VENV_DIR' using pyenv's Python $PYTHON_VERSION_TARGET..."
    if ! python -m venv "$VENV_DIR"; then # 'python' should now be the pyenv version
        print_error_exit "Failed to create virtual environment using 'python -m venv $VENV_DIR'."
    fi
    PYTHON_EXEC="$VENV_DIR/bin/python"
else
    print_info "pyenv not found."
    print_info "Attempting to use system '$PYTHON_COMMAND_FALLBACK' to create virtual environment '$VENV_DIR'..."
    if command_exists "$PYTHON_COMMAND_FALLBACK"; then
        if ! "$PYTHON_COMMAND_FALLBACK" -m venv "$VENV_DIR"; then
            print_error_exit "Failed to create virtual environment using '$PYTHON_COMMAND_FALLBACK -m venv $VENV_DIR'."
        fi
        PYTHON_EXEC="$VENV_DIR/bin/python"
    else
        original_error_message="'$PYTHON_COMMAND_FALLBACK' command not found.\nPlease install Python $PYTHON_COMMAND_FALLBACK (matching $PYTHON_VERSION_TARGET if possible),\nor install pyenv (https://github.com/pyenv/pyenv), install Python $PYTHON_VERSION_TARGET via pyenv, and then re-run this script."
        print_warning "$original_error_message"
        attempt_pyenv_install_guidance # Ask user if they want to install pyenv
        # If attempt_pyenv_install_guidance was skipped or user said no, exit with the original error.
        print_error_exit "$original_error_message"
    fi
fi

print_info "Virtual environment '$VENV_DIR' created successfully."
echo ""

print_info "Activating virtual environment for script execution..."
source "$VENV_DIR/bin/activate"

print_info "Upgrading pip, setuptools, and wheel using '$PYTHON_EXEC' from venv..."
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
echo "  For Windows:     $VENV_DIR\\Scripts\\activate" # Escaped backslash for Windows path
echo ""
echo "Then, you can run the server with: python app.py"
echo "---------------------------------------------------------------------"
