# llm_analyzer.py
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Please set it in .env")

genai.configure(api_key=API_KEY)
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", 'gemini-1.5-flash-latest')
try:
    model = genai.GenerativeModel(MODEL_NAME)
    print(f"LLM Analyzer initialized with model: {MODEL_NAME}")
except Exception as e:
    print(f"ERROR initializing Gemini Model '{MODEL_NAME}': {e}")
    model = None

SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


def parse_llm_response_structured(analysis_text):
    parsed = {"Explanation": "N/A", "Relevance": "N/A", "IoCs": "N/A",
              "Mitigation": "N/A", "Further_Investigation": "N/A"}



    # Split by known keys to find sections
    sections = {}
    current_section_key = None

    # Define keys in the order they are expected to appear (or any order if not strict)

    known_keys_in_order = [
        "Explanation:", "Relevance:", "IoCs:",
        "Suggested Mitigation:", "Further Investigation Steps:"
    ]

    # Split the text into lines to process
    lines = analysis_text.split('\n')

    temp_buffer = []

    for line in lines:
        line_stripped = line.strip()

        found_new_key = False
        for key_prefix in known_keys_in_order:
            if line_stripped.startswith(key_prefix):
                # If a new key is found, save the buffer for the previous key
                if current_section_key and temp_buffer:
                    # Map the prompt key to the dictionary key
                    if current_section_key == "Explanation:":
                        parsed_key = "Explanation"
                    elif current_section_key == "Relevance:":
                        parsed_key = "Relevance"
                    elif current_section_key == "IoCs:":
                        parsed_key = "IoCs"
                    elif current_section_key == "Suggested Mitigation:":
                        parsed_key = "Mitigation"
                    elif current_section_key == "Further Investigation Steps:":
                        parsed_key = "Further_Investigation"
                    else:
                        parsed_key = None

                    if parsed_key:
                        parsed[parsed_key] = " ".join(temp_buffer).strip()

                # Start new buffer for the new key
                current_section_key = key_prefix
                temp_buffer = [line_stripped.replace(key_prefix, "").strip()]
                found_new_key = True
                break  # Move to next line once a key is matched

        if not found_new_key and current_section_key:
            # If it's not a new key line, append to the current buffer
            if line_stripped:  # Append only if non-empty after stripping
                temp_buffer.append(line_stripped)

    # Save the last buffer
    if current_section_key and temp_buffer:
        if current_section_key == "Explanation:":
            parsed_key = "Explanation"
        elif current_section_key == "Relevance:":
            parsed_key = "Relevance"
        elif current_section_key == "IoCs:":
            parsed_key = "IoCs"
        elif current_section_key == "Suggested Mitigation:":
            parsed_key = "Mitigation"
        elif current_section_key == "Further Investigation Steps:":
            parsed_key = "Further_Investigation"
        else:
            parsed_key = None

        if parsed_key:
            parsed[parsed_key] = " ".join(temp_buffer).strip()

    # Fallback if main parsing yields mostly N/A but text exists
    all_na = all(v == "N/A" for k, v in parsed.items() if
                 k != "Mitigation" and k != "Further_Investigation")  # Check primary fields
    if all_na and any(key_prefix in analysis_text for key_prefix in
                      known_keys_in_order[:3]):  # Check if at least one primary key exists
        try:
            # print("DEBUG: Using fallback parsing for LLM response.")
            for line in analysis_text.split('\n'):
                if line.startswith("Explanation:"):
                    parsed["Explanation"] = line.split(":", 1)[1].strip() if ":" in line else line
                elif line.startswith("Relevance:"):
                    parsed["Relevance"] = line.split(":", 1)[1].strip() if ":" in line else line
                elif line.startswith("IoCs:"):
                    parsed["IoCs"] = line.split(":", 1)[1].strip() if ":" in line else line
                elif line.startswith("Suggested Mitigation:"):
                    parsed["Mitigation"] = line.split(":", 1)[1].strip() if ":" in line else line
                elif line.startswith("Further Investigation Steps:"):
                    parsed["Further_Investigation"] = line.split(":", 1)[1].strip() if ":" in line else line
        except IndexError:
            print("Warning: LLM response parsing fallback (IndexError). Assigning full text to Explanation.")
            parsed["Explanation"] = analysis_text
        if parsed["Explanation"] == "N/A" and analysis_text.strip():  # Absolute fallback
            parsed["Explanation"] = analysis_text

    return parsed


def analyze_log_entry_with_gemini(log_summary_for_llm):
    if not model: return {"Explanation": "LLM Model not initialized.", "Relevance": "Error", "IoCs": "Error"}
    prompt = f"""
    You are a Cybersecurity Log Analysis Assistant.
    Analyze the following Windows log entry summary. Provide a concise explanation, its security relevance, and any potential IoCs.

    Log Entry Summary:
    ---
    {log_summary_for_llm}
    ---

    Tasks:
    1. **Explanation:** Briefly explain what this log event typically means (1-2 sentences).
    2. **Security Relevance:** Categorize as "Informational", "Low", "Medium", "High", "Critical". Justify briefly.
    3.  **Potential IoCs:** List any obvious Indicators of Compromise. This includes:
    - Suspicious IP addresses or domain names.
    - Full paths to suspicious files or executables.
    - Usernames *directly involved in executing suspicious commands or associated with suspicious processes as the primary actor*. Do not list usernames that are merely contextual (e.g., the user running the logging service) unless they are the active agent in the event.
    - Known malicious hashes.
    If none directly related to suspicious activity, state "None apparent".

    Format your response STRICTLY as follows:
    Explanation: [Your explanation]
    Relevance: [Category] - [Justification]
    IoCs: [IoCs or "None apparent"]
    """
    try:
        response = model.generate_content(prompt, safety_settings=SAFETY_SETTINGS)
        return parse_llm_response_structured(response.text)
    except Exception as e:
        print(f"Error querying Gemini (analyze_log_entry): {e}")
        feedback_info = "N/A";
        error_response_text = ""
        if hasattr(e, 'response') and e.response:  # Check if response attribute exists and is not None
            if hasattr(e.response, 'prompt_feedback') and e.response.prompt_feedback:
                feedback_info = f"Blocked: {e.response.prompt_feedback.block_reason}"
            if hasattr(e.response, 'text'): error_response_text = e.response.text
        elif hasattr(e, 'message') and "blocked" in str(e.message).lower():
            feedback_info = "Blocked by safety settings."
        return {"Explanation": f"LLM Error: {str(e)}. Feedback: {feedback_info}. Details: {error_response_text[:200]}",
                "Relevance": "Error", "IoCs": "Error"}


def get_deep_dive_llm_analysis(full_log_summary_for_llm):
    if not model: return {"Explanation": "LLM Model not initialized.", "Relevance": "Error", "IoCs": "Error",
                          "Mitigation": "N/A", "Further_Investigation": "N/A"}
    prompt = f"""
    You are an Expert Cybersecurity Forensic Analyst providing a deep dive into a specific Windows log entry.
    Analyze the comprehensive log entry details provided below.

    Log Entry Details:
    ---
    {full_log_summary_for_llm}
    ---

    Provide a detailed analysis covering the following, using Markdown for formatting where appropriate (like lists for IoCs, Mitigation, Steps):
    1.  **Explanation:** In-depth explanation of the event, its components, and what specific activity it represents.
    2.  **Security Relevance:** Detailed assessment (Informational, Low, Medium, High, Critical), considering context. Explain WHY it has that relevance.
    3.  **Potential IoCs:** Enumerate all potential Indicators of Compromise (IPs, domains, file paths, hashes, user accounts, registry keys, etc.). Be specific. If none, state "None apparent". Use bullet points if multiple.
    4.  **Suggested Mitigation:** If suspicious/malicious, suggest potential mitigation or hardening steps. If benign, state "No mitigation needed". Use bullet points if multiple.
    5.  **Further Investigation Steps:** Specific next steps for an analyst. Use bullet points if multiple.

    Format your response STRICTLY as follows, with each section starting on a new line:
    Explanation: [Detailed explanation]
    Relevance: [Category] - [Detailed justification]
    IoCs: 
    - [IoC 1 (if any)]
    - [IoC 2 (if any)]
    Suggested Mitigation:
    - [Mitigation 1 (if any)]
    - [Mitigation 2 (if any)]
    Further Investigation Steps:
    - [Step 1 (if any)]
    - [Step 2 (if any)]
    """
    try:
        response = model.generate_content(prompt, safety_settings=SAFETY_SETTINGS)
        return parse_llm_response_structured(response.text)
    except Exception as e:
        print(f"Error querying Gemini (get_deep_dive): {e}")
        feedback_info = "N/A";
        error_response_text = ""
        if hasattr(e, 'response') and e.response:
            if hasattr(e.response, 'prompt_feedback') and e.response.prompt_feedback:
                feedback_info = f"Blocked: {e.response.prompt_feedback.block_reason}"
            if hasattr(e.response, 'text'): error_response_text = e.response.text
        elif hasattr(e, 'message') and "blocked" in str(e.message).lower():
            feedback_info = "Blocked by safety settings."
        return {"Explanation": f"LLM Error: {str(e)}. Feedback: {feedback_info}. Details: {error_response_text[:200]}",
                "Relevance": "Error", "IoCs": "Error",
                "Mitigation": "Error contacting LLM", "Further_Investigation": "Error contacting LLM"}


# --- NEW FUNCTION FOR PDF REPORT SUMMARY ---
def get_report_summary_llm(log_samples_summary_string, original_filename):
    """
    Generates an executive summary for a report based on a sample of log summaries.
    log_samples_summary_string: A string containing concatenated raw_summary_for_llm for a few logs.
    original_filename: The name of the log file being analyzed.
    """
    if not model: return "LLM Model not initialized. Cannot generate report summary."
    if not log_samples_summary_string or not log_samples_summary_string.strip():
        return "No log samples provided to generate a summary."

    prompt = f"""
    You are a Cybersecurity Analyst preparing an executive summary for a log analysis report.
    The report is for the log file: "{original_filename}".
    Below is a sample of key log entries found (these are summaries, not full logs).

    Sampled Log Entry Summaries:
    ---
    {log_samples_summary_string}
    ---

    Task:
    Based *only* on the provided sampled log summaries, write a concise executive summary (2-4 paragraphs) for the PDF report.
    This summary should:
    1. Briefly state the overall nature of the observed activities in the provided log samples (e.g., routine operations, potential reconnaissance, indications of compromise).
    2. Highlight any particularly noteworthy or suspicious patterns, key event types, or recurring IoCs observed *in these samples*.
    3. If there are clear indications of malicious activity in the samples, mention them. If the samples seem mostly benign or informational, state that.
    4. Conclude with a brief statement on the general security posture indicated *by these specific samples only*.

    Do NOT invent details not present in the provided summaries.
    Keep the language professional and suitable for a report.
    Do NOT refer to this prompt or the fact that these are samples in your summary.
    """
    try:
        response = model.generate_content(prompt, safety_settings=SAFETY_SETTINGS)
        # For this summary, we typically just want the raw text block.
        # No need for the complex structured parsing unless you add specific sections to the prompt.
        summary_text = response.text.strip()
        if not summary_text:
            return "LLM generated an empty summary."
        return summary_text
    except Exception as e:
        print(f"Error querying Gemini for report summary: {e}")
        feedback_info = "N/A";
        error_response_text = ""
        if hasattr(e, 'response') and e.response:
            if hasattr(e.response, 'prompt_feedback') and e.response.prompt_feedback:
                feedback_info = f"Blocked: {e.response.prompt_feedback.block_reason}"
            if hasattr(e.response, 'text'): error_response_text = e.response.text
        elif hasattr(e, 'message') and "blocked" in str(e.message).lower():
            feedback_info = "Blocked by safety settings."
        return f"Error generating AI summary for report: {str(e)}. Feedback: {feedback_info}. Details: {error_response_text[:200]}"