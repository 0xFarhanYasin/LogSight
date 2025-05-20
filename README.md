# LogSight Pro: AI-Powered Windows Event Log Analysis Platform

LogSight Pro is an advanced web-based application designed to parse, analyze, and provide intelligent, actionable insights from Windows Event Logs (.evtx files). It uniquely leverages Google's Gemini Large Language Model (LLM) to offer deep explanations of log events, assess their security relevance, identify potential Indicators of Compromise (IoCs), and suggest next steps for investigation.

This tool empowers security analysts, incident responders, and system administrators to quickly understand complex log data, identify suspicious activities, and accelerate their investigative workflows.

## Key Features

*   **Robust EVTX Parsing:** Utilizes Eric Zimmerman's `EvtxECmd.exe` (via subprocess) for thorough and accurate parsing of Windows `.evtx` log files, including Security, System, Application, and Sysmon logs.
*   **AI-Driven Analysis (Google Gemini):**
    *   **Initial Triage:** Provides a concise LLM-generated explanation, security relevance (Informational to Critical), and potential IoCs for processed log entries.
    *   **"Deep Dive" Analysis:** Offers an in-depth forensic analysis for individual log entries on demand, including detailed explanations, richer IoC enumeration, suggested mitigations, and further investigation steps.
    *   **AI Executive Summary for Reports:** Generates a contextual summary of observed activities for PDF reports based on sampled logs.
*   **Interactive Dashboard & Visualization:**
    *   Presents key statistics from log files, such as top Event IDs, log level distribution, and top event providers, through interactive Plotly charts.
    *   Tabbed interface for clear separation of file management and detailed analysis views.
*   **Advanced Log Filtering & Search:**
    *   Filter detailed logs by date range, keyword (searching descriptions, LLM explanations, and raw summaries), Event ID, Level, and Provider.
    *   Dynamically populated dropdowns for Level and Provider based on the content of the selected log file.
    *   "Clear Filters" functionality for ease of use.
*   **Paginated Log View:** Efficiently displays large numbers of log entries with pagination.
*   **PDF Report Generation:** Allows users to download comprehensive PDF reports of the currently filtered log view, including the AI-generated executive summary and detailed log entries with their LLM analysis.
*   **Modern Dark-Themed UI:** Built with Dash Bootstrap Components (VAPOR theme) for a professional and visually appealing user experience.
*   **Persistent Storage:** Uses SQLite to store information about uploaded files, parsed logs, and LLM analysis results.

## Technologies & Architecture

*   **Backend & Web Framework:** Python, Dash (by Plotly)
*   **Frontend (via Dash):** Dash Bootstrap Components, Plotly.js (for charts)
*   **Log Parsing Engine:** `EvtxECmd.exe` (by Eric Zimmerman) - Integrated via Python's `subprocess` module.
*   **AI/LLM Integration:** Google Gemini API (e.g., `gemini-1.5-flash-latest` or user-configured model).
*   **Database:** SQLite for data persistence.
*   **PDF Generation:** ReportLab library.
*   **Data Manipulation:** Pandas.
*   **Environment Management:** `python-dotenv` for API key management.

## Project Structure Overview
Use code with caution.
```bash
logsight-pro/
├── .env.example # Example environment file for API keys
├── .gitignore # Specifies intentionally untracked files
├── app.py # Main Dash application: UI layout and callbacks
├── database.py # SQLite database schema and interaction functions
├── llm_analyzer.py # Handles all interactions with the Google Gemini API, including prompts
├── log_parser.py # Manages calling EvtxECmd and processing its CSV output
├── pdf_generator.py # Logic for creating PDF analysis reports
├── requirements.txt # Python package dependencies
├── uploaded_logs_temp/ # Temporary storage for uploads (created automatically, in .gitignore)
└── README.md # This file
```
## Setup and Installation

**Prerequisites:**

1.  **Python:** Version 3.9 or newer recommended.
2.  **Google Gemini API Key:**
    *   Obtain an API key from [Google AI Studio](https://aistudio.google.com/).
3.  **EvtxECmd.exe (External Tool):**
    *   Download Eric Zimmerman's command-line tools from his official website: [https://ericzimmerman.github.io/](https://ericzimmerman.github.io/).
    *   Extract `EvtxECmd.exe` (and any accompanying DLLs from the same archive, typically `EvtxECmd.deps.json` and `EvtxECmd.runtimeconfig.json` if present for .NET core versions) to a chosen directory on your system.

**Installation Steps:**

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/LogSight-Pro.git 
    # Replace YOUR_USERNAME with your GitHub username
    cd LogSight-Pro
    ```

2.  **Create and Activate a Python Virtual Environment:**
    ```bash
    python -m venv venv
    # On Windows:
    venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    *   Create a file named `.env` in the project's root directory (you can copy `.env.example` if provided).
    *   Add your Google Gemini API key and optionally specify the model:
        ```env
        GEMINI_API_KEY="YOUR_ACTUAL_GEMINI_API_KEY"
        GEMINI_MODEL_NAME="gemini-1.5-flash-latest" # Or another suitable model
        ```

5.  **Configure `EvtxECmd.exe` Path:**
    *   Open the `log_parser.py` file.
    *   Find the `EVTXECMD_PATH` variable at the top.
    *   **Crucially, update this path** to the exact location of your `EvtxECmd.exe` executable.
        ```python
        # Example:
        EVTXECMD_PATH = r"C:\Tools\ZimmermanTools\EvtxECmd.exe"
        ```

## Running LogSight Pro

1.  **Ensure your virtual environment is activated.**
2.  **Initialize the Database (Run once if the `logsight_data.db` file doesn't exist):**
    The application will attempt to initialize the database on startup (`db.init_db()` in `app.py`). You can also run it manually if needed:
    ```bash
    python database.py 
    ```

3.  **Start the Dash Application:**
    ```bash
    python app.py
    ```

4.  Open your web browser and navigate to the URL shown in the console (typically `http://127.0.0.1:8050/`).

## How to Use

1.  **Upload:** Navigate to the "Log File Management" tab and upload your Windows `.evtx` log file.
2.  **Process:** Wait for the file to be processed. Status updates will appear, and the "Processed Log Files" table will refresh.
3.  **Select & Analyze:** Click on a processed file in the table. This will activate the "Dashboard & Detailed Analysis" tab.
4.  **Dashboard View:** Review the overview charts (Event IDs, Levels, Providers).
5.  **Filter Logs:** Use the filter controls (Date Range, Keyword, Event ID, Level, Provider) to refine the "Detailed Logs" table. Click "Clear Filters" to reset.
6.  **Deep Dive:** In the "Detailed Logs" table, click on a log's "ID" to open a modal with an in-depth AI analysis for that specific entry.
7.  **Download Report:** Click the "Download PDF Report" button to generate a PDF of the currently selected file, incorporating applied filters and an AI executive summary.

## Known Limitations & Future Work

*   Currently focused on Windows `.evtx` logs due to reliance on `EvtxECmd.exe`.
*   File processing is synchronous; very large files might cause the UI to hang during processing. (Future: Background tasks with Celery/Redis).
*   Error handling for `EvtxECmd.exe` issues can be further enhanced.
*   LLM prompt engineering is an ongoing process for optimal results across diverse log types.
*   Consider adding support for other log formats (syslog, application text logs, CSV, JSON).
*   More advanced interactive visualizations and log correlation features.

## Contributing
<!-- If you want contributions -->
Contributions are welcome! Please feel free to fork the repository, make changes, and submit a pull request. For major changes, please open an issue first to discuss what you would like to change.

## License
<!-- Choose a license if you want, e.g., MIT -->
This project is licensed under the MIT License - see the LICENSE.md file (if you create one) for details.
