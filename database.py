# database.py
import sqlite3
import pandas as pd
from datetime import datetime

DATABASE_NAME = 'logsight_data.db'


def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS log_files (
        file_id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL,
        upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'Pending',
        total_entries INTEGER DEFAULT 0, parsed_entries INTEGER DEFAULT 0,
        analyzed_entries INTEGER DEFAULT 0, error_message TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS parsed_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT, file_id INTEGER NOT NULL,
        timestamp TEXT, event_id TEXT, provider TEXT, level TEXT, computer TEXT,
        description TEXT, raw_summary_for_llm TEXT,
        FOREIGN KEY (file_id) REFERENCES log_files (file_id)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS llm_analysis (
        analysis_id INTEGER PRIMARY KEY AUTOINCREMENT, log_id INTEGER NOT NULL,
        llm_explanation TEXT, llm_relevance TEXT, llm_iocs TEXT,
        analysis_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (log_id) REFERENCES parsed_logs (log_id)
    )
    ''')
    conn.commit()
    conn.close()


def add_log_file_record(filename):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO log_files (filename) VALUES (?)", (filename,))
    file_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return file_id


def update_log_file_status(file_id, status, total_entries=None, parsed_entries=None, analyzed_entries=None,
                           error_message=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    update_fields = {"status": status}
    if total_entries is not None: update_fields["total_entries"] = total_entries
    if parsed_entries is not None: update_fields["parsed_entries"] = parsed_entries
    if analyzed_entries is not None: update_fields["analyzed_entries"] = analyzed_entries
    if error_message is not None: update_fields["error_message"] = error_message
    set_clause = ", ".join([f"{key} = ?" for key in update_fields.keys()])
    values = list(update_fields.values()) + [file_id]
    cursor.execute(f"UPDATE log_files SET {set_clause} WHERE file_id = ?", values)
    conn.commit()
    conn.close()


def get_all_log_files():
    conn = get_db_connection()
    df = pd.read_sql_query(
        "SELECT file_id, filename, upload_timestamp, status, total_entries, error_message FROM log_files ORDER BY upload_timestamp DESC",
        conn)
    conn.close()
    return df


def get_log_file_details(file_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM log_files WHERE file_id = ?", (file_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def bulk_insert_parsed_logs(file_id, parsed_logs_df):
    if parsed_logs_df.empty: return 0
    conn = get_db_connection()
    parsed_logs_df['file_id'] = file_id
    db_columns = ['file_id', 'timestamp', 'event_id', 'provider', 'level', 'computer', 'description',
                  'raw_summary_for_llm']
    df_to_insert = parsed_logs_df[[col for col in db_columns if col in parsed_logs_df.columns]]
    try:
        df_to_insert.to_sql('parsed_logs', conn, if_exists='append', index=False)
        inserted_count = len(df_to_insert)
    except Exception as e:
        print(f"Error during bulk insert: {e}")
        inserted_count = 0
        raise e
    finally:
        conn.close()
    return inserted_count


def get_parsed_logs_for_file(file_id, page=1, page_size=20,
                             keyword_search=None, filter_event_id=None,
                             filter_level=None, filter_provider=None,
                             date_start=None, date_end=None):  # New date filters
    conn = get_db_connection()
    offset = (page - 1) * page_size
    params = []
    where_clauses = ["pl.file_id = ?"]
    params.append(file_id)

    if keyword_search:
        where_clauses.append("(pl.description LIKE ? OR la.llm_explanation LIKE ? OR pl.raw_summary_for_llm LIKE ?)")
        params.extend([f"%{keyword_search}%", f"%{keyword_search}%", f"%{keyword_search}%"])
    if filter_event_id:
        where_clauses.append("LOWER(pl.event_id) = LOWER(?)")
        params.append(filter_event_id)
    if filter_level:
        where_clauses.append("LOWER(pl.level) = LOWER(?)")
        params.append(filter_level)
    if filter_provider:
        where_clauses.append("pl.provider LIKE ?")
        params.append(f"%{filter_provider}%")
    if date_start:  # Expects YYYY-MM-DD
        where_clauses.append("pl.timestamp >= ?")
        params.append(f"{date_start}T00:00:00.000")  # Compare against start of day
    if date_end:  # Expects YYYY-MM-DD
        where_clauses.append("pl.timestamp <= ?")
        params.append(f"{date_end}T23:59:59.999")  # Compare against end of day

    where_sql = " AND ".join(where_clauses)
    query = f"""
    SELECT pl.log_id, pl.timestamp, pl.event_id, pl.provider, pl.level, 
           pl.computer, pl.description, pl.raw_summary_for_llm, -- Added raw_summary_for_llm for deep dive
           la.llm_explanation, la.llm_relevance, la.llm_iocs
    FROM parsed_logs pl LEFT JOIN llm_analysis la ON pl.log_id = la.log_id
    WHERE {where_sql} ORDER BY pl.timestamp ASC, pl.log_id ASC LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    df = pd.read_sql_query(query, conn, params=tuple(params))
    conn.close()
    return df


def get_parsed_log_count_for_file(file_id, keyword_search=None, filter_event_id=None,
                                  filter_level=None, filter_provider=None,
                                  date_start=None, date_end=None):  # New date filters
    conn = get_db_connection()
    cursor = conn.cursor()
    params = []
    base_query = "SELECT COUNT(DISTINCT pl.log_id) FROM parsed_logs pl LEFT JOIN llm_analysis la ON pl.log_id = la.log_id"
    where_clauses = ["pl.file_id = ?"]
    params.append(file_id)

    if keyword_search:
        where_clauses.append("(pl.description LIKE ? OR la.llm_explanation LIKE ? OR pl.raw_summary_for_llm LIKE ?)")
        params.extend([f"%{keyword_search}%", f"%{keyword_search}%", f"%{keyword_search}%"])
    if filter_event_id: where_clauses.append("LOWER(pl.event_id) = LOWER(?)"); params.append(filter_event_id)
    if filter_level: where_clauses.append("LOWER(pl.level) = LOWER(?)"); params.append(filter_level)
    if filter_provider: where_clauses.append("pl.provider LIKE ?"); params.append(f"%{filter_provider}%")
    if date_start: where_clauses.append("pl.timestamp >= ?"); params.append(f"{date_start}T00:00:00.000")
    if date_end: where_clauses.append("pl.timestamp <= ?"); params.append(f"{date_end}T23:59:59.999")

    where_sql = " AND ".join(where_clauses)
    final_query = f"{base_query} WHERE {where_sql}"
    cursor.execute(final_query, tuple(params))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def add_llm_analysis(log_id, analysis_results):
    conn = get_db_connection()
    cursor = conn.cursor()
    explanation = analysis_results.get('Explanation', 'N/A')
    relevance = analysis_results.get('Relevance', 'N/A')
    iocs = analysis_results.get('IoCs', 'N/A')
    cursor.execute("""
    INSERT INTO llm_analysis (log_id, llm_explanation, llm_relevance, llm_iocs, analysis_timestamp)
    VALUES (?, ?, ?, ?, ?) """, (log_id, explanation, relevance, iocs, datetime.now()))
    conn.commit()
    conn.close()


def get_parsed_logs_without_llm_analysis(file_id, limit=5):
    conn = get_db_connection()
    query = """
    SELECT pl.log_id, pl.raw_summary_for_llm FROM parsed_logs pl
    LEFT JOIN llm_analysis la ON pl.log_id = la.log_id
    WHERE pl.file_id = ? AND la.analysis_id IS NULL ORDER BY RANDOM() LIMIT ? 
    """
    df = pd.read_sql_query(query, conn, params=(file_id, limit))
    conn.close()
    return df


def get_event_id_counts(file_id):
    conn = get_db_connection()
    query = "SELECT event_id, COUNT(*) as count FROM parsed_logs WHERE file_id = ? GROUP BY event_id ORDER BY count DESC"
    df = pd.read_sql_query(query, conn, params=(file_id,))
    conn.close()
    return df


def get_level_counts(file_id):
    conn = get_db_connection()
    query = "SELECT level, COUNT(*) as count FROM parsed_logs WHERE file_id = ? GROUP BY level ORDER BY count DESC"
    df = pd.read_sql_query(query, conn, params=(file_id,))
    conn.close()
    return df


def get_provider_counts(file_id):
    conn = get_db_connection()
    query = "SELECT provider, COUNT(*) as count FROM parsed_logs WHERE file_id = ? GROUP BY provider ORDER BY count DESC LIMIT 10"
    df = pd.read_sql_query(query, conn, params=(file_id,))
    conn.close()
    return df


def get_full_log_entry_details(log_id):
    conn = get_db_connection()
    # Fetch all relevant fields for a deep dive
    query = """
    SELECT pl.log_id, pl.timestamp, pl.event_id, pl.provider, pl.level, 
           pl.computer, pl.description, pl.raw_summary_for_llm,
           la.llm_explanation, la.llm_relevance, la.llm_iocs
    FROM parsed_logs pl
    LEFT JOIN llm_analysis la ON pl.log_id = la.log_id
    WHERE pl.log_id = ?
    """
    cursor = conn.cursor()
    cursor.execute(query, (log_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_unique_levels_for_file(file_id):
    conn = get_db_connection()
    # Ensure level is not empty or just whitespace
    query = """
    SELECT DISTINCT level
    FROM parsed_logs
    WHERE file_id = ? AND level IS NOT NULL AND TRIM(level) != ''
    ORDER BY level ASC
    """
    df = pd.read_sql_query(query, conn, params=(file_id,))
    conn.close()
    return df['level'].tolist()


def get_unique_providers_for_file(file_id):
    conn = get_db_connection()
    # Ensure provider is not empty or just whitespace
    query = """
    SELECT DISTINCT provider
    FROM parsed_logs
    WHERE file_id = ? AND provider IS NOT NULL AND TRIM(provider) != ''
    ORDER BY provider ASC
    """
    df = pd.read_sql_query(query, conn, params=(file_id,))
    conn.close()
    return df['provider'].tolist()


if __name__ == '__main__':
    init_db()
    print(f"Database '{DATABASE_NAME}' tables ensured/created and ready.")
