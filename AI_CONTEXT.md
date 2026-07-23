# AI Context for Kindle to PDF Converter

## Project Overview
This project is a tool to capture Kindle for PC books and convert them into PDF files. It works by automating page turns and taking screenshots, then stitching them into a PDF.

## Architecture
The project consists of three main components:
1.  **`main.py`**: The entry point of the application. It handles argument parsing and orchestrates the capture and conversion process.
2.  **`src/capturer.py`**: Handles the interaction with the Kindle for PC application. It finds/activates the Kindle window, auto-detects page-turn direction (ltr/rtl), automates page turning and screen capturing using `pyautogui`, waits for visual settle via burst frame diffs, and auto-stops when consecutive screenshots are nearly identical.
3.  **`src/converter.py`**: Handles the conversion of captured screenshots into a single PDF file using `img2pdf`.
4.  **`src/ocr_namer.py`**: OCRs the first captured page (Windows OCR via `winocr`) and suggests an output PDF filename from the leading characters.
5.  **`src/splitter.py`**: A utility to split PDFs by page count (not used in the main flow).
## Usage
### Prerequisites
-   Windows OS
-   Python installed
-   Kindle for PC installed

### Installation
```powershell
pip install -r requirements.txt
```

### Running the Converter
1. Open the target book in Kindle for PC.
2. Run:
```powershell
python main.py
```
Or with an explicit output name:
```powershell
python main.py --output my_book.pdf
```
3. Press Enter. The tool tries to bring Kindle to the foreground, enter fullscreen (F11), then captures pages until the last page is detected (or `--pages` is reached). If `--output` is omitted, the first page is OCR'd to build the filename.

Options:
-   `--output`: Output PDF filename (optional; default: OCR auto-name from page 1)
-   `--name-chars`: Max characters from OCR used in the auto filename (default: `40`)
-   `--temp-dir`: Temporary directory for screenshots (default: `screenshots`)
-   `--pages`: Number of pages to capture (optional; default: auto-stop on last page)
-   `--direction`: Page direction (`auto` by default, or `ltr` / `rtl`)
-   `--max-size`: Maximum size of generated PDF (default: `180MB`)
-   `--delay`: Max seconds to wait for the page to visually settle after a turn (default: `2.0`; burst-captures and adopts a frame once frame-to-frame diff stays small)
## Directory Structure
-   `main.py`: Main script.
-   `src/`: Source code directory.
    -   `capturer.py`: Screen capture logic (window focus, auto-stop, progress).
    -   `converter.py`: Image to PDF conversion logic.
    -   `ocr_namer.py`: OCR-based output filename suggestion.
    -   `splitter.py`: PDF splitting logic.
-   `screenshots/`: Default directory for temporary screenshots (gitignored).
-   `output/`: Default directory for output files (gitignored).
-   `requirements.txt`: Python dependencies.
-   `README.md`: User documentation.
-   `AI_CONTEXT.md`: This file.
