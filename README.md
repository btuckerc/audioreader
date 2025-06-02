# Local Audiobook Server with Whisper Captioning

This project provides a minimal, self-hosted server that uses OpenAI's Whisper to generate VTT (Web Video Text Tracks) captions for your local audio (MP3) files. It is designed for users who want to create and view synchronized transcripts for their audio content. Maybe to read a book while listening to an audiobook. The application organizes MP3s into folders, treating each folder as a "book" or collection. It features a web interface to browse these collections, manage transcription generation, and an integrated player to listen to audio with its accompanying captions.

While named "audiobook server," it can be used for any collection of MP3 files you wish to transcribe and play sequentially, such as lectures, podcasts, or personal recordings.

## Features

*   **Self-Hosted:** Runs locally on your computer.
*   **Whisper Integration:** Utilizes OpenAI's Whisper (via its command-line interface) to generate VTT caption files for MP3s.
    *   Attempts to enable word-level timestamps and highlighting if supported by your Whisper installation, for more precise caption synchronization.
*   **Web Interface:**
    *   Browse audio collections (organized as subdirectories within the `audioreader/books/` directory).
    *   View the transcription status for each audio file (VTT exists or not, presence of word-level timestamps).
    *   Check if a transcription job is currently running for a file.
    *   Initiate transcription generation for individual MP3 files or for all untranscribed files within a "book."
    *   Option for parallel transcription of multiple files within a book (default 2 workers).
    *   Test Whisper transcription speed for different models and VTT generation settings (word timestamps, highlighting) using a 15-second audio clip. Speed test results are saved in `speed_ratios.json`.
    *   View estimated processing times for files based on saved speed ratios.
*   **Audio Player:**
    *   Integrated HTML5 audio player.
    *   Displays synchronized VTT captions alongside the audio.
    *   Playlist functionality for playing through multiple tracks in a "book."
*   **Backend:** Built with Python and Flask.
*   **Directory Setup:** The `books` directory (for storing audio) and `audiobooks_app.log` (for logging) are created automatically by `app.py` on startup if they don't exist.

## Prerequisites

Before running the `setup.sh` script, ensure you have the following generally available on your system:

*   **`bash`:** To execute the `setup.sh` script.
*   **Standard Build Tools:** If `pyenv` needs to install Python from source (e.g., if a pre-compiled binary isn't available for your system for version `3.11.8`), you'll need standard build tools (like `gcc`, `make`, `libssl-dev`, `zlib1g-dev`, etc., depending on your OS). `pyenv install <version>` usually provides guidance if dependencies are missing.
*   **`ffmpeg` (and `ffprobe`):**
    *   These are crucial for full application functionality: creating test audio clips for speed tests and getting accurate audio durations.
    *   The `setup.sh` script will check if `ffmpeg` and `ffprobe` are accessible in your system's PATH. If not, it will provide guidance on how to install them for common operating systems.
    *   It is highly recommended to install `ffmpeg` before or immediately after running `setup.sh` if the script indicates they are missing.
*   **Python Version Management (Recommended: `pyenv`):**
    *   The `setup.sh` script is designed to work best with `pyenv` ([https://github.com/pyenv/pyenv](https://github.com/pyenv/pyenv)) for managing Python versions. It will attempt to install and use Python `3.11.8` (or the version specified in `PYTHON_VERSION_TARGET` within the script) via `pyenv`.
    *   If `pyenv` is not found, the script will attempt to use a fallback command `python3.11` to set up the environment.
    *   If neither `pyenv` can set up the target Python version nor the fallback `python3.11` command is found/functional, the script will guide you on how to proceed (e.g., install `pyenv` or the required Python version manually).
    *   Having `pip` (Python package installer, usually comes with Python) is implicitly required for the Python installation that `setup.sh` ultimately uses.

## Installation

1.  **Clone the Repository:**
    Open your terminal or command prompt and run:
    ```bash
    git clone https://github.com/btuckerc/audioreader.git
    cd audioreader
    ```

2.  **Run the Setup Script:**
    This script performs several actions to set up your Python environment and install dependencies:
    *   **`ffmpeg` Check:** Verifies if `ffmpeg` and `ffprobe` are installed and guides you if they are missing.
    *   **Python Environment Setup (using `pyenv` if available):**
        *   If `pyenv` is detected, it attempts to install Python `3.11.8` (or the `PYTHON_VERSION_TARGET` in the script) if not already installed by `pyenv`.
        *   It then sets this Python version as the local version for the `audioreader` directory by creating/updating a `.python-version` file.
        *   It uses this `pyenv`-managed Python to create a virtual environment named `venv`.
        *   If `pyenv` is not found, it attempts to use `python3.11` (the `PYTHON_COMMAND_FALLBACK` in the script) to create the `venv`.
        *   If Python setup fails, the script will provide an error message and exit.
    *   **Virtual Environment Activation (for script):** Activates the `venv` *within the script's execution* to install packages correctly.
    *   **Dependency Installation:** Installs `Flask` and `openai-whisper` (and their dependencies) into `venv` using `pip` from the created virtual environment.
    *   **Guidance:** Provides clear instructions on how to manually activate `venv` in your terminal for running the application.

    Execute the script from the `audioreader` directory:
    ```bash
    bash setup.sh
    ```
    *If you encounter a permission error, you might need to make the script executable first: `chmod +x setup.sh`*

    **Important Note on Virtual Environment Activation:** The `setup.sh` script activates `venv` only for its own execution. Once the script finishes, `venv` will NOT be active in your terminal. You MUST activate it manually before running the application (see next section).

## Preparing Your Audio Files

1.  **Locate the `books` Directory:**
    Inside the `audioreader` project folder, a directory named `books` will be automatically created by `app.py` when you first run the server if it's not already present. This is where the application looks for your audio files.

2.  **Organize Your Audio:**
    *   Inside the `audioreader/books/` directory, create a separate sub-folder for each collection of MP3s you want to treat as a distinct "book" or album (e.g., an audiobook, a lecture series).
    *   Place your MP3 files for that collection directly into its respective sub-folder.

    Example folder structure:
    ```
    audioreader/
    ├── .python-version      (created by setup.sh if pyenv is used)
    ├── app.py
    ├── setup.sh
    ├── books/
    │   ├── Name of Book/
    │   │   ├── chapter_01.mp3
    │   │   ├── chapter_02.mp3
    │   │   └── ...
    │   └── Podcast Series Title/
    │       ├── Episode_01.mp3
    │       ├── Episode_02.mp3
    │       └── ...
    ├── static/
    ├── templates/
    ├── venv/                (Python virtual environment)
    ├── speed_ratios.json  (created after first speed test)
    ├── audiobooks_app.log (created on first app run)
    ├── README.md
    ├── LICENSE
    └── .gitignore
    ```

## Running the Server

1.  **Navigate to the Project Directory:**
    Open your terminal and ensure you are in the `audioreader` directory.
    ```bash
    cd path/to/your/audioreader
    ```

2.  **Activate the Virtual Environment:**
    Before running the application, you **must** activate the `venv` virtual environment that `setup.sh` prepared. In your current terminal session, run:
    ```bash
    source venv/bin/activate  # On macOS/Linux
    # For Windows: venv\Scripts\activate
    ```
    Your terminal prompt will usually change to indicate that the `venv` is active. If `pyenv` was used during setup, this `venv` will be using the Python version specified by the `.python-version` file (e.g., `3.11.8`).

3.  **Run the Application:**
    With the `venv` active, start the server:
    ```bash
    python app.py
    ```
    *(Using `python` instead of `python3` or `python3.11` is correct here because the activated `venv` ensures `python` points to the virtual environment's interpreter.)*

4.  **Access the Web Interface:**
    You should see a message in your terminal indicating the server is running, typically including a line like:
    `Audiobooks server running. Access at http://localhost:8000 (Model: medium)`
    Open your web browser and go to `http://localhost:8000`.

## Usage Guide

*   **Main Page (`/`):**
    *   Lists all "books" (subdirectories found in `audioreader/books/`).
*   **Book Page (`/book/<book_name>/`):**
    *   Accessed by clicking a book title on the main page.
    *   Lists all MP3 files for the selected book.
    *   Displays current Whisper model used for transcriptions (e.g., "medium" - this is configurable in `app.py`).
    *   For each MP3, shows data retrieved via `/api/book/<book_name>/file-info`:
        *   Audio duration (requires `ffprobe`) and file size.
        *   Transcription status: "VTT exists" or not.
        *   Word-level timestamp status within the VTT if it exists (depends on Whisper capabilities and VTT content).
        *   If a transcription job is currently active for this file.
    *   **Actions for each file:**
        *   "Generate Transcript": Initiates transcription for that single MP3 using options (word timestamps, highlighting) selected in the UI. These options are passed to the `whisper` CLI if supported.
    *   **Actions for the book:**
        *   "Generate All Missing Transcripts": Initiates transcription for all MP3s in the current book that do not yet have VTT files. Can be run sequentially or in parallel (default 2 workers, configurable in `app.py`). UI-selected transcription options apply.
        *   "Test Transcription Speed":
            *   Allows testing the speed of the current `MODEL` (defined in `app.py`) with UI-selected VTT generation options.
            *   Uses a 15-second clip (created using `ffmpeg`) from a file in the book.
            *   Saves the speed ratio (audio duration / processing time) to `speed_ratios.json`, keyed by model and settings.
            *   Displays estimated processing times for other files in the book based on this new ratio.
*   **Transcription Log/Stream:**
    *   When transcription is initiated, a log stream appears on the page, showing real-time output from the Whisper CLI, including the command used and progress messages.
*   **Player Page (`/player/<book_name>/`):**
    *   Accessible once at least one track in a book has a VTT caption file.
    *   Presents a playlist of all tracks in the book that have captions.
    *   Plays the audio with synchronized VTT captions displayed.

## How Transcriptions Are Generated

*   **Whisper CLI:** The server calls the `whisper` command-line tool to perform speech-to-text.
*   **Background Processing:** Transcription jobs run as background processes via Python's `subprocess.Popen`, allowing the web UI to remain responsive.
*   **VTT Options (Word Timestamps & Highlighting):**
    *   The application backend (`app.py`) checks Whisper CLI capabilities (using `whisper --help`) to see if `--word_timestamps` and `--highlight_words` arguments are supported.
    *   If these features are supported by Whisper and enabled by the user in the web interface when starting a transcription, they are passed to the `whisper` command.
*   **Output:** VTT files are saved in the same directory as their corresponding MP3s (e.g., for `chapter_01.mp3`, the caption file will be `chapter_01.vtt`).
*   **Model:** The Whisper model used for transcription is determined by the global `MODEL` variable in `app.py` (default is "medium").

## Customization

*   **Whisper Model:**
    *   To change the default Whisper model for transcriptions and speed tests, modify the `MODEL` variable at the top of `audioreader/app.py`.
    *   Available models generally include `tiny`, `base`, `small`, `medium`, `large`. Smaller models are faster but less accurate; larger models are more accurate but slower and require more resources.
    *   Restart the server (`python app.py`) after changing the model in `app.py`.
*   **Parallel Transcription Workers:**
    *   When using "Generate All Missing Transcripts" with the parallel option, the default number of workers is 2. This is set in the `whisper_stream_parallel` function in `app.py` (parameter `max_workers=2`). Modify this value in `app.py` and restart the server if you need a different number of parallel jobs.
*   **Logging:**
    *   Application logs (startup, errors, warnings, info from `app.logger`) are saved to `audioreader/audiobooks_app.log`. This file is created automatically by `app.py` if it doesn't exist.
    *   Log rotation is configured in `app.py` (default: 10MB per file, 5 backup files).

## Contributing

Contributions, bug reports, and feature suggestions are welcome. Please feel free to open an issue or submit a pull request on the GitHub repository: [https://github.com/btuckerc/audioreader](https://github.com/btuckerc/audioreader).

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPLv3). See the `LICENSE` file for the full text.

This license means:
*   You are free to use, study, share, and modify this software.
*   If you distribute modified versions, you must also distribute the source code of your modifications under the same AGPLv3 license.
*   **Network Service Provision:** If you run a modified version of this software and offer it as a service over a network, you must also provide the source code of your modified version to the users of that service.
*   Appropriate credit should be given to the original project.

This license is chosen to ensure the software and any improvements made to it remain free and open for everyone to use and build upon.
