# log_parser.py

import pandas as pd
import subprocess
import os
import tempfile
import xml.etree.ElementTree as ET
import re

EVTXECMD_PATH = r"C:\Tools\ZimmermanTools\EvtxECmd.exe"  # Your path


def parse_xml_payload(xml_string):
    details = {}
    try:
        cleaned_xml_string = xml_string.replace('\x00', '').strip()
        if not cleaned_xml_string or not cleaned_xml_string.startswith("<"):
            return details
        root = ET.fromstring(cleaned_xml_string)
        for elem in root.iter():
            name = elem.get('Name')
            text_content = elem.text.strip() if elem.text else None
            if name and text_content:
                details[name] = text_content
            elif not name and text_content and elem.tag and not list(elem):  # Leaf node with text
                tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if tag_name in details and isinstance(details[tag_name], list):
                    details[tag_name].append(text_content)
                elif tag_name in details:
                    details[tag_name] = [details[tag_name], text_content]
                else:
                    details[tag_name] = text_content
    except ET.ParseError:
        details["XmlPayload_Unparsed"] = xml_string[:500]
    except Exception:
        details["XmlPayload_Error"] = xml_string[:500]
    return details


def parse_generic_payload_as_kv(payload_string):
    details = {}
    try:
        normalized_payload = payload_string.replace('\r\n', '\n').replace('\r', '\n')
        pairs = re.split(r';\s*|\n', normalized_payload)
        for pair_str in pairs:
            pair_str = pair_str.strip()
            if not pair_str: continue
            match = re.match(r'^\s*([a-zA-Z0-9_.\s-]+?)\s*:\s*(.*)$', pair_str)
            if match:
                key, value = match.groups()
                details[key.strip()] = value.strip()
        if not details and payload_string.strip():
            details['PayloadText'] = payload_string
    except Exception:
        details['KeyValueParseError_RawPayload'] = payload_string
    return details


def parse_evtx_file_with_evtxecmd(input_evtx_path, max_entries=None):
    if not os.path.exists(EVTXECMD_PATH):
        print(f"ERROR: EvtxECmd.exe not found at '{EVTXECMD_PATH}'. Update path.")
        return pd.DataFrame([{"Error": "EvtxECmd.exe not configured or found."}])

    with tempfile.TemporaryDirectory() as temp_dir:
        command = [EVTXECMD_PATH, "-f", input_evtx_path, "--csv", temp_dir]
        # print(f"Running command: {' '.join(command)}") # Keep for debugging if needed

        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            stdout, stderr = process.communicate(timeout=300)

            if process.returncode != 0:
                error_msg = f"EvtxECmd failed. Code: {process.returncode}.\nStderr: {stderr.decode(errors='ignore')}\nStdout: {stdout.decode(errors='ignore')}"
                print(error_msg)
                return pd.DataFrame([{"Error": error_msg}])

            generated_csv_files = [f for f in os.listdir(temp_dir) if f.endswith(".csv")]
            if not generated_csv_files:
                return pd.DataFrame(
                    [{"Error": f"EvtxECmd ran, but no CSV in '{temp_dir}'.\nStdout: {stdout.decode(errors='ignore')}"}])

            actual_csv_path = os.path.join(temp_dir, generated_csv_files[0])
            # print(f"EvtxECmd successful. Reading CSV: {actual_csv_path}")
            df = pd.read_csv(actual_csv_path, low_memory=False, na_filter=False, dtype=str)

            

            if df.empty: return pd.DataFrame()  # Return early if CSV is empty

            if max_entries is not None: df = df.head(max_entries)

            parsed_data_list = []
            known_handled_columns = ['Timestamp (UTC)', 'Timestamp', 'TimeCreated', 'TimeGenerated', 'RecordTime',
                                     'EventId', 'Provider', 'LevelText', 'Level', 'Computer', 'Message',
                                     'PayloadData', 'EventData']

            for _, row in df.iterrows():
                row_dict = row.to_dict()
                possible_ts_names = ['Timestamp (UTC)', 'Timestamp', 'TimeCreated', 'TimeGenerated', 'RecordTime']
                timestamp_str = ''
                for name in possible_ts_names:
                    if name in row_dict and row_dict[name]:
                        timestamp_str = row_dict[name]
                        break
                try:
                    # Attempt to parse and reformat to ensure consistency for SQLite
                    pd_dt = pd.to_datetime(timestamp_str, errors='coerce')
                    # Use YYYY-MM-DD HH:MM:SS.sss format if possible, which SQLite handles well for comparisons
                    timestamp = pd_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] if pd.notna(pd_dt) else timestamp_str
                    if pd.isna(pd_dt) and timestamp_str:  # if parsing failed but original string exists
                        timestamp = timestamp_str  # keep original possibly non-standard string
                    elif pd.isna(pd_dt) and not timestamp_str:
                        timestamp = ""  # Ensure it's an empty string if totally unparsable
                except Exception:
                    timestamp = timestamp_str if timestamp_str else ""

                event_id = row_dict.get('EventId', "N/A")
                provider = row_dict.get('Provider', "N/A")
                level = row_dict.get('LevelText', row_dict.get('Level', "N/A"))
                computer = row_dict.get('Computer', "N/A")
                description = row_dict.get('Message', "").strip()
                if not description: description = f"Event ID {event_id} from {provider}."

                llm_summary_data = {
                    "Time": timestamp, "EventID": event_id, "Provider": provider,
                    "Level": level, "Computer": computer,
                    "EvtxECmd_Message": description if description != f"Event ID {event_id} from {provider}." else ""
                }
                llm_summary_data = {k: v for k, v in llm_summary_data.items() if str(v).strip()}

                payload_content = row_dict.get('PayloadData', row_dict.get('EventData', '')).strip()
                if payload_content:
                    payload_details = {}
                    if payload_content.startswith("<"):
                        payload_details = parse_xml_payload(payload_content)
                    else:
                        payload_details = parse_generic_payload_as_kv(payload_content)
                    for k, v_payload in payload_details.items():
                        clean_key = "Payload_" + re.sub(r'[^a-zA-Z0-9_]', '', k)
                        if clean_key and str(v_payload).strip():
                            llm_summary_data[clean_key] = str(v_payload)

                for col_name, col_value in row_dict.items():
                    if col_name not in known_handled_columns and col_name not in llm_summary_data:
                        col_value_str = str(col_value).strip()
                        if col_value_str:
                            clean_col_name = "Other_" + re.sub(r'[^a-zA-Z0-9_]', '', col_name.replace(" ", "_"))
                            llm_summary_data[clean_col_name] = col_value_str

                raw_summary_for_llm = ", ".join(
                    [f"{k}: {str(v)[:300]}" for k, v in llm_summary_data.items() if str(v).strip()])
                if not raw_summary_for_llm:
                    raw_summary_for_llm = f"Basic_Info: Time: {timestamp}, EventID: {event_id}, Provider: {provider}, Level: {level}, Computer: {computer}"

                parsed_data_list.append({
                    'timestamp': timestamp, 'event_id': event_id, 'provider': provider,
                    'level': level, 'computer': computer,
                    'description': description[:1000],
                    'raw_summary_for_llm': raw_summary_for_llm
                })

            if not parsed_data_list: return pd.DataFrame()
            final_df = pd.DataFrame(parsed_data_list)
            target_cols = ['timestamp', 'event_id', 'provider', 'level', 'computer', 'description',
                           'raw_summary_for_llm']
            for col in target_cols:
                if col not in final_df.columns:
                    final_df[
                        col] = "" if col == 'timestamp' else "N/A_SCHEMA_FILL"  # Use empty string for timestamp if missing
            return final_df[target_cols]
        except subprocess.TimeoutExpired:
            return pd.DataFrame([{"Error": "EvtxECmd command timed out."}])
        except FileNotFoundError:
            return pd.DataFrame([{"Error": f"EvtxECmd.exe not found at '{EVTXECMD_PATH}'."}])
        except Exception as e:
            import traceback
            print(f"Error in parser's main try-except block: {e}")
            print(traceback.format_exc())
            return pd.DataFrame([{"Error": f"General error in parser: {e}"}])
