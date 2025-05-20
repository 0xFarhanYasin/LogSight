# app.py
import dash
from dash import dcc, html, dash_table, ctx, no_update
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import base64, io, os, pandas as pd, plotly.express as px
from datetime import date, datetime  # Added datetime for PDF filename

# Import your custom modules
import database as db
from log_parser import parse_evtx_file_with_evtxecmd  # Ensure this matches your parser function name
from llm_analyzer import analyze_log_entry_with_gemini, get_deep_dive_llm_analysis, get_report_summary_llm
import pdf_generator  # Ensure this file exists and is correct

# --- Configuration ---
UPLOAD_DIRECTORY = "uploaded_logs_temp"
if not os.path.exists(UPLOAD_DIRECTORY): os.makedirs(UPLOAD_DIRECTORY)
MAX_ENTRIES_TO_PARSE_FROM_FILE = 1000
LLM_ANALYSIS_SAMPLE_SIZE = 5
LOG_DETAILS_PAGE_SIZE = 15
PDF_SUMMARY_LOG_SAMPLE_SIZE = 20

db.init_db()

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.VAPOR], suppress_callback_exceptions=True)
server = app.server

# --- App Layout ---
app.layout = dbc.Container([
    dcc.Location(id='url', refresh=False),
    dcc.Download(id="download-pdf-report"),
    dbc.Row(dbc.Col(html.H1("LogSight Pro: Intelligent Log Analysis", className="text-center my-4"), width=12)),
    dbc.Tabs(id="app-tabs", active_tab="tab-manage", children=[
        dbc.Tab(label="Log File Management", tab_id="tab-manage", children=[
            dbc.Row([
                dbc.Col(html.H4("Upload New Log File (.evtx)", className="mt-3 mb-3"), width=12),
                dbc.Col(dcc.Upload(id='upload-log-data',
                                   children=html.Div(['Drag & Drop or ', html.A('Select .evtx File')]),
                                   style={'width': '100%', 'height': '60px', 'lineHeight': '60px', 'borderWidth': '1px',
                                          'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center',
                                          'margin': '10px 0px'}),
                        width=12),
                dbc.Col(html.Div(id='upload-status-message', className="mt-2"), width=12)
            ], className="mb-4"),
            html.Hr(),
            dbc.Row([
                dbc.Col(html.H4("Processed Log Files", className="mb-3"), width=12),
                dbc.Col(dcc.Loading(id="loading-processed-files-table", type="default",
                                    children=[html.Div(id='processed-files-table-container')]), width=12),
                dbc.Col(dbc.Button("Refresh Files List", id="refresh-files-button", className="mt-3", color="secondary",
                                   size="sm"), width={"size": "auto"})
            ], className="mb-4"),
        ]),
        dbc.Tab(label="Dashboard & Detailed Analysis", tab_id="tab-dashboard",
                children=[html.Div(id="dashboard-and-details-content", className="mt-3")])
    ]),
    dcc.Store(id='selected-file-id-store', data=None),
    dcc.Store(id='current-log-page-store', data=1),
    dcc.Store(id='current-filters-store', data={}),
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="deep-dive-modal-title", style={'color': '#E9ECEF'})),
        dbc.ModalBody(
            dcc.Loading(id="loading-deep-dive", type="default", children=[html.Div(id="deep-dive-modal-content")])),
        dbc.ModalFooter(dbc.Button("Close", id="close-deep-dive-modal", color="secondary", className="ml-auto"))
    ], id="deep-dive-modal", size="xl", scrollable=True, is_open=False, backdrop="static", centered=True,
        style={'backgroundColor': 'rgba(40, 43, 48, 0.9)'}  # Removed content_classname
    )
], fluid=True, className="dbc")


# --- Helper Functions ---
def save_uploaded_file_temp(name, content):
    if content is None: return None
    try:
        _, content_string = content.split(','); decoded = base64.b64decode(content_string)
    except Exception as e:
        print(f"Error decoding base64 content: {e}"); return None
    file_path = os.path.join(UPLOAD_DIRECTORY, name)
    try:
        with open(file_path, "wb") as fp:
            fp.write(decoded)
        return file_path
    except Exception as e:
        print(f"Error saving temp file {name}: {e}"); return None


def process_uploaded_log_file(physical_file_path, original_filename):
    file_id = None
    try:
        file_id = db.add_log_file_record(original_filename)
        db.update_log_file_status(file_id, status="Processing")
        parsed_df = parse_evtx_file_with_evtxecmd(physical_file_path, max_entries=MAX_ENTRIES_TO_PARSE_FROM_FILE)
        if "Error" in parsed_df.columns and not parsed_df["Error"].isna().all():
            error_msg = parsed_df["Error"].iloc[0];
            db.update_log_file_status(file_id, status="Error", error_message=str(error_msg));
            return f"Error during parsing: {error_msg}"
        if parsed_df.empty:
            db.update_log_file_status(file_id, status="Processed", total_entries=0, parsed_entries=0);
            return "No log entries found."
        total_entries_in_file = len(parsed_df)
        db.update_log_file_status(file_id, status="Processing", total_entries=total_entries_in_file)
        if 'raw_summary_for_llm' not in parsed_df.columns and 'description' in parsed_df.columns:
            parsed_df['raw_summary_for_llm'] = parsed_df['description']
        elif 'raw_summary_for_llm' not in parsed_df.columns:
            parsed_df['raw_summary_for_llm'] = "Log summary not available."
        inserted_count = db.bulk_insert_parsed_logs(file_id, parsed_df)
        db.update_log_file_status(file_id, status="Processing", parsed_entries=inserted_count)
        logs_for_llm_sample_df = db.get_parsed_logs_without_llm_analysis(file_id, limit=LLM_ANALYSIS_SAMPLE_SIZE)
        analyzed_count = 0
        if not logs_for_llm_sample_df.empty:
            for _, row in logs_for_llm_sample_df.iterrows():
                log_id_val = row['log_id'];
                log_summary = row['raw_summary_for_llm']
                if pd.notna(log_summary) and str(log_summary).strip():
                    try:
                        analysis_results = analyze_log_entry_with_gemini(log_summary); db.add_llm_analysis(log_id_val,
                                                                                                           analysis_results); analyzed_count += 1
                    except Exception as e_llm:
                        print(f"LLM analysis failed for log_id {log_id_val}: {e_llm}")
        db.update_log_file_status(file_id, status="Processed", analyzed_entries=analyzed_count)
        return f"File '{original_filename}' processed. {inserted_count} logs stored. {analyzed_count} logs initially analyzed."
    except Exception as e:
        print(f"Error processing file {original_filename}: {e}");
        import traceback;
        traceback.print_exc()
        if file_id: db.update_log_file_status(file_id, status="Error", error_message=str(e))
        return f"Processing error: {e}"
    finally:
        if physical_file_path and os.path.exists(physical_file_path):
            try:
                os.remove(physical_file_path)
            except Exception as e_remove:
                print(f"Warning: Could not remove temp file {physical_file_path}: {e_remove}")


def create_processed_files_datatable(data_records):
    return dash_table.DataTable(
        id='processed-files-table',
        columns=[{"name": "ID", "id": "file_id"}, {"name": "Filename", "id": "filename"},
                 {"name": "Uploaded", "id": "upload_timestamp"}, {"name": "Status", "id": "status"},
                 {"name": "Total Logs", "id": "total_entries"},
                 {"name": "Error", "id": "error_message", "type": "text", "presentation": "markdown"}],
        data=data_records, row_selectable='single', selected_rows=[], page_size=5,
        style_header={'backgroundColor': 'rgb(45,45,45)', 'fontWeight': 'bold', 'color': 'white',
                      'border': '1px solid rgb(70,70,70)'},
        style_cell={'textAlign': 'left', 'whiteSpace': 'normal', 'height': 'auto', 'minWidth': '50px',
                    'maxWidth': '280px', 'backgroundColor': 'rgb(60,60,60)', 'color': '#adb5bd',
                    'border': '1px solid rgb(70,70,70)'},
        style_filter={'backgroundColor': 'rgb(70,70,70)', 'color': 'white', 'border': '1px solid rgb(90,90,90)'},
        style_table={'overflowX': 'auto'}, filter_action="native", sort_action="native")


@app.callback(Output('processed-files-table-container', 'children'),
              [Input('url', 'pathname'), Input('refresh-files-button', 'n_clicks'),
               Input('upload-status-message', 'children')])
def update_processed_files_display(pathname, refresh_clicks, upload_status_children):
    return create_processed_files_datatable(db.get_all_log_files().to_dict('records'))


@app.callback(Output('upload-status-message', 'children'), [Input('upload-log-data', 'contents')],
              [State('upload-log-data', 'filename')], prevent_initial_call=True)
def handle_file_upload(uploaded_content, uploaded_filename):
    if uploaded_content is None: return no_update
    if not uploaded_filename.lower().endswith('.evtx'): return dbc.Alert("Only .evtx files supported.", color="danger",
                                                                         dismissable=True)
    path = save_uploaded_file_temp(uploaded_filename, uploaded_content)
    if not path: return dbc.Alert("Failed to save temp file.", color="danger", dismissable=True)
    msg = process_uploaded_log_file(path, uploaded_filename)
    color = "success" if "processed" in msg.lower() else "danger" if "error" in msg.lower() else "warning"
    return dbc.Alert(msg, color=color, dismissable=True, duration=10000)


@app.callback(Output('selected-file-id-store', 'data'), [Input('processed-files-table', 'selected_rows')],
              [State('processed-files-table', 'data')])
def store_selected_file_id(selected_rows_indices, table_data):
    if not selected_rows_indices or not table_data or not isinstance(table_data, list) or not selected_rows_indices[
                                                                                                  0] < len(
        table_data): return None
    return table_data[selected_rows_indices[0]].get('file_id')


@app.callback(Output('dashboard-and-details-content', 'children'), [Input('selected-file-id-store', 'data')])
def render_dashboard_and_details_tab(selected_file_id):
    if selected_file_id is None:
        return dbc.Alert("Select a log file from 'Log File Management' tab to view dashboard and details.",
                         color="info", className="mt-4 text-center")
    details = db.get_log_file_details(selected_file_id)
    filename = details['filename'] if details else "Selected File"
    today = date.today()
    return html.Div([
        dbc.Row(dbc.Col(html.H3(f"Analysis Dashboard for: {filename}", className="text-center my-3"))),
        dbc.Row([dbc.Col(dcc.Loading(dcc.Graph(id='event-id-counts-chart')), lg=6, md=12, className="mb-3"),
                 dbc.Col(dcc.Loading(dcc.Graph(id='level-counts-chart')), lg=6, md=12, className="mb-3")],
                className="mt-2"),
        dbc.Row([dbc.Col(dcc.Loading(dcc.Graph(id='provider-counts-chart')), lg=6, md=12, className="mb-3")]),
        html.Hr(className="my-4"),
        dbc.Row([
            dbc.Col(html.H5("Filter Detailed Logs:", className="mt-1 mb-2"), width=12),
            dbc.Col(dcc.DatePickerRange(id='date-picker-range', start_date_placeholder_text="Start Date",
                                        end_date_placeholder_text="End Date",
                                        min_date_allowed=date(2000, 1, 1),
                                        max_date_allowed=date(today.year + 5, 12, 31),
                                        initial_visible_month=today, display_format='YYYY-MM-DD',
                                        className="dash-date-picker-override"),
                    width=12, xxl=3, xl=4, lg=12, className="mb-2"),
            dbc.Col(dbc.Input(id="filter-keyword", placeholder="Search Text...", type="text", debounce=True, size="sm"),
                    width=12, xxl=3, xl=4, lg=12, className="mb-2"),
            dbc.Col(dbc.Input(id="filter-event-id", placeholder="Event ID...", type="text", debounce=True, size="sm"),
                    width=6, xxl=1, xl=2, lg=6, className="mb-2"),
            # Adjusted Dropdown style for VAPOR theme
            dbc.Col(dcc.Dropdown(id="filter-level-dropdown", placeholder="Level", clearable=True,
                                 className="dash-dropdown-override",
                                 style={'color': '#495057', 'backgroundColor': '#2a2b2d'}), width=6, xxl=2, xl=2, lg=6,
                    className="mb-2"),
            dbc.Col(dcc.Dropdown(id="filter-provider-dropdown", placeholder="Provider", clearable=True,
                                 className="dash-dropdown-override",
                                 style={'color': '#495057', 'backgroundColor': '#2a2b2d'}), width=12, xxl=2, xl=4,
                    lg=12, className="mb-2"),
            dbc.Col(dbc.Button("Clear Filters", id="clear-filters-button", outline=True, color="light", size="sm"),
                    width="auto", className="mb-2 align-self-end")
        ], className="mb-1 align-items-center g-1"),
        dbc.Row([dbc.Col(dbc.Button("Download PDF Report", id="download-report-button", color="primary", size="sm"),
                         width="auto", className="mt-2 mb-2")]),
        dbc.Row([
            dbc.Col(html.H4(id="selected-file-logs-header", className="mt-3"), width=12),
            dbc.Col(dcc.Loading(id="loading-log-details-table", children=[html.Div(id='log-details-table-container')]),
                    width=12),
            dbc.Col(
                [dbc.Pagination(id="log-pagination", max_value=1, first_last=True, previous_next=True, active_page=1)],
                width=12, className="mt-3 d-flex justify-content-center")
        ])
    ])


CHART_TEMPLATE = "plotly_dark";
PLOT_BG_COLOR = "rgba(0,0,0,0)";
TABLE_STYLE_COMMON = {'backgroundColor': 'rgb(60,60,60)', 'color': '#adb5bd', 'border': '1px solid rgb(70,70,70)'}
MODAL_CARD_COLOR = "dark"


@app.callback(Output('filter-level-dropdown', 'options'), [Input('selected-file-id-store', 'data')])
def update_level_filter_options(file_id):
    if file_id is None: return []
    return [{'label': lvl, 'value': lvl} for lvl in db.get_unique_levels_for_file(file_id)]


@app.callback(Output('filter-provider-dropdown', 'options'), [Input('selected-file-id-store', 'data')])
def update_provider_filter_options(file_id):
    if file_id is None: return []
    return [{'label': prov, 'value': prov} for prov in db.get_unique_providers_for_file(file_id)]


@app.callback([Output('filter-keyword', 'value'), Output('filter-event-id', 'value'),
               Output('filter-level-dropdown', 'value'), Output('filter-provider-dropdown', 'value'),
               Output('date-picker-range', 'start_date'), Output('date-picker-range', 'end_date')],
              [Input('clear-filters-button', 'n_clicks')], prevent_initial_call=True)
def clear_filter_inputs(n_clicks):
    if n_clicks: return "", "", None, None, None, None
    return [no_update] * 6


@app.callback(Output('event-id-counts-chart', 'figure'), [Input('selected-file-id-store', 'data')])
def update_event_id_chart(file_id):
    if file_id is None:
        fig = px.bar(title="Event ID Counts")
    else:
        df = db.get_event_id_counts(file_id)
        if df.empty:
            fig = px.bar(title="Event ID Counts: No Data")
        else:
            fig = px.bar(df.head(15), x='event_id', y='count', title='Top 15 Event IDs', text_auto=True,
                         labels={'event_id': 'Event ID', 'count': 'Count'})
    fig.update_layout(template=CHART_TEMPLATE, paper_bgcolor=PLOT_BG_COLOR, plot_bgcolor=PLOT_BG_COLOR,
                      font_color="white")
    return fig


@app.callback(Output('level-counts-chart', 'figure'), [Input('selected-file-id-store', 'data')])
def update_level_chart(file_id):
    if file_id is None:
        fig = px.pie(title="Log Level Distribution")
    else:
        df = db.get_level_counts(file_id)
        if df.empty:
            fig = px.pie(title="Log Level Distribution: No Data")
        else:
            fig = px.pie(df, names='level', values='count', title='Log Level Distribution', hole=0.4)
    fig.update_layout(template=CHART_TEMPLATE, paper_bgcolor=PLOT_BG_COLOR, plot_bgcolor=PLOT_BG_COLOR,
                      legend=dict(bgcolor="rgba(40,40,40,0.5)", bordercolor="rgba(100,100,100,0.5)",
                                  font_color="white"), font_color="white")
    return fig


@app.callback(Output('provider-counts-chart', 'figure'), [Input('selected-file-id-store', 'data')])
def update_provider_chart(file_id):
    if file_id is None:
        fig = px.bar(title="Top Log Providers")
    else:
        df = db.get_provider_counts(file_id)
        if df.empty:
            fig = px.bar(title="Top Log Providers: No Data")
        else:
            fig = px.bar(df, y='provider', x='count', title='Top Log Providers', orientation='h', text_auto=True,
                         labels={'provider': 'Provider', 'count': 'Count'})
    fig.update_layout(yaxis_title=None, xaxis_title="Count", yaxis={'categoryorder': 'total ascending'},
                      template=CHART_TEMPLATE, paper_bgcolor=PLOT_BG_COLOR, plot_bgcolor=PLOT_BG_COLOR,
                      font_color="white")
    return fig


@app.callback(Output('current-filters-store', 'data'),
              [Input('filter-keyword', 'value'), Input('filter-event-id', 'value'),
               Input('filter-level-dropdown', 'value'), Input('filter-provider-dropdown', 'value'),
               Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')])
def store_current_filters(kw, eid, lvl, prov, start_date, end_date):
    return {"keyword": kw, "event_id": eid, "level": lvl, "provider": prov,
            "date_start": start_date, "date_end": end_date}


@app.callback(
    [Output('log-details-table-container', 'children'),
     Output('selected-file-logs-header', 'children'),
     Output('log-pagination', 'max_value'),
     Output('log-pagination', 'active_page')],
    [Input('selected-file-id-store', 'data'), Input('log-pagination', 'active_page'),
     Input('current-filters-store', 'data')],
    [State('current-log-page-store', 'data')])
def display_log_details(file_id, page_from_pgn, current_filters, stored_page):
    header = "Log Details";
    table_content = html.Div();
    max_pgs = 1;
    page = 1
    if file_id is None: return table_content, header, max_pgs, page

    kw = current_filters.get("keyword");
    eid = current_filters.get("event_id")
    lvl = current_filters.get("level");
    prov = current_filters.get("provider")
    date_start = current_filters.get("date_start");
    date_end = current_filters.get("date_end")

    # Correctly determine the source of the callback trigger
    # triggered_id_info will be the string ID of the component (e.g., 'log-pagination', 'selected-file-id-store', 'current-filters-store')
    triggered_id_info = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered and ctx.triggered[
        0] else 'selected-file-id-store'  # Added check for ctx.triggered[0]

    if triggered_id_info == 'log-pagination' and page_from_pgn is not None:
        page = page_from_pgn
    elif triggered_id_info == 'selected-file-id-store' or triggered_id_info == 'current-filters-store':  # CORRECTED HERE
        page = 1
    elif stored_page is not None:
        page = stored_page
    # else page remains 1 (its default from initialization)

    details = db.get_log_file_details(file_id)
    header = f"Detailed Logs for: {details['filename']} (ID: {file_id})" if details else "Log Details"

    logs_df = db.get_parsed_logs_for_file(file_id, page, LOG_DETAILS_PAGE_SIZE, kw, eid, lvl, prov, date_start,
                                          date_end)
    total_logs = db.get_parsed_log_count_for_file(file_id, kw, eid, lvl, prov, date_start, date_end)
    max_pgs = (total_logs + LOG_DETAILS_PAGE_SIZE - 1) // LOG_DETAILS_PAGE_SIZE if total_logs > 0 else 1

    # Adjust page if it's out of bounds after filtering or file change
    if page > max_pgs: page = max_pgs if max_pgs > 0 else 1
    if page == 0 and max_pgs > 0: page = 1  # Ensure page is at least 1 if there are pages

    # Re-fetch if page was adjusted due to max_pgs changing OR if it was a filter/file change and we reset to page 1 (and page 1 wasn't what pagination naturally had)
    # This logic aims to ensure the data matches the determined 'page'
    current_page_from_pagination_input = page_from_pgn if page_from_pgn is not None else page  # Use current 'page' if pagination wasn't trigger
    if page != current_page_from_pagination_input and (
            triggered_id_info in ['selected-file-id-store', 'current-filters-store']):
        logs_df = db.get_parsed_logs_for_file(file_id, page, LOG_DETAILS_PAGE_SIZE, kw, eid, lvl, prov, date_start,
                                              date_end)

    if logs_df.empty:
        table_content = html.P("No logs found matching your criteria.", className="text-muted mt-3 text-center")
    else:
        data_for_table = logs_df.to_dict('records')
        cols_map = {"log_id": "ID", "timestamp": "Time", "event_id": "EID", "provider": "Provider",
                    "level": "Lvl", "description": "Desc.", "llm_explanation": "LLM Notes",
                    "llm_relevance": "LLM Risk", "llm_iocs": "LLM IoCs"}

        # Ensure 'log_id' is always included in data_for_table for the modal, even if not in cols_map for display
        # The current cols_map includes "log_id": "ID", so it should be fine.

        table_cols = [{"name": v, "id": k, "type": "text",
                       "presentation": "markdown" if k == "log_id" else "input"}
                      # 'log_id' (displayed as 'ID') made markdown for potential styling
                      for k, v in cols_map.items() if k in logs_df.columns]

        table_content = dash_table.DataTable(
            id='log_details_actual_table', columns=table_cols, data=data_for_table, page_action='none',
            style_cell={'textAlign': 'left', 'whiteSpace': 'normal', 'height': 'auto', 'minWidth': '50px',
                        'maxWidth': '250px',
                        'overflow': 'hidden', 'textOverflow': 'ellipsis', **TABLE_STYLE_COMMON},
            style_header={'backgroundColor': 'rgb(30,30,30)', 'fontWeight': 'bold', 'color': 'white',
                          'border': '1px solid rgb(70,70,70)'},
            style_table={'overflowX': 'auto', 'marginTop': '15px'},
            tooltip_data=[{c['id']: {'value': str(row.get(c['id'], '')), 'type': 'markdown'} for c in table_cols} for
                          row in data_for_table],
            tooltip_duration=None, cell_selectable=True)  # cell_selectable for deep dive trigger

    return table_content, header, max_pgs, page


@app.callback(
    [Output("deep-dive-modal", "is_open"), Output("deep-dive-modal-title", "children"),
     Output("deep-dive-modal-content", "children")],
    [Input("log_details_actual_table", "active_cell"), Input("close-deep-dive-modal", "n_clicks")],
    [State("deep-dive-modal", "is_open"), State("log_details_actual_table", "data")],
    prevent_initial_call=True)
def toggle_deep_dive_modal(active_cell, n_close, is_open, table_data):
    # CORRECTED: Use ctx.triggered_id which is a dictionary or string
    triggered_input_info = ctx.triggered[0] if ctx.triggered else None
    triggered_id = triggered_input_info['prop_id'].split('.')[0] if triggered_input_info else None

    if triggered_id == "log_details_actual_table" and active_cell and table_data:
        row_idx = active_cell['row'];
        col_id = active_cell['column_id']
        if col_id == 'ID':
            log_id_from_table = table_data[row_idx].get('log_id')  # Use .get() for safety
            if log_id_from_table is None:  # If 'log_id' key somehow missing, or using 'ID' from renamed cols
                log_id_from_table = table_data[row_idx].get('ID')

            if log_id_from_table is not None:
                log_details_db = db.get_full_log_entry_details(log_id_from_table)
                if log_details_db and log_details_db.get('raw_summary_for_llm'):
                    title = f"Deep Dive: Log ID {log_id_from_table} (EID: {log_details_db.get('event_id', 'N/A')})"
                    llm_analysis = get_deep_dive_llm_analysis(log_details_db['raw_summary_for_llm'])
                    content = [
                        html.H6("Original Basic LLM Analysis:", className="mt-3 text-info"),
                        dbc.Card([dbc.CardBody([
                            html.P([html.Strong("Explanation: "), log_details_db.get('llm_explanation', 'N/A')]),
                            html.P([html.Strong("Relevance: "), log_details_db.get('llm_relevance', 'N/A')]),
                            html.P([html.Strong("IoCs: "), log_details_db.get('llm_iocs', 'N/A')]),
                        ])], className="mb-3", color=MODAL_CARD_COLOR, inverse=True),
                        html.H5("Deep Dive LLM Analysis:", className="mt-4 text-info"),
                        dbc.Card([dbc.CardBody([
                            html.Strong("Detailed Explanation:"),
                            dcc.Markdown(llm_analysis.get('Explanation', 'N/A'), className="mb-2 markdown-in-modal"),
                            html.Strong("Security Relevance Assessment:"),
                            dcc.Markdown(llm_analysis.get('Relevance', 'N/A'), className="mb-2 markdown-in-modal"),
                            html.Strong("Potential IoCs:"),
                            dcc.Markdown(llm_analysis.get('IoCs', 'N/A'), className="mb-2 markdown-in-modal"),
                            html.Strong("Suggested Mitigation:"),
                            dcc.Markdown(llm_analysis.get('Mitigation', 'N/A'), className="mb-2 markdown-in-modal"),
                            html.Strong("Further Investigation Steps:"),
                            dcc.Markdown(llm_analysis.get('Further_Investigation', 'N/A'),
                                         className="mb-2 markdown-in-modal"),
                        ])], color=MODAL_CARD_COLOR, inverse=True)]
                    return True, title, content
                return True, f"Error for Log ID: {log_id_from_table}", html.P("Details not found for deep dive.")
            else:  # log_id_from_table was None
                return no_update, no_update, no_update  # Or some error message in modal

    elif triggered_id == "close-deep-dive-modal":
        return False, "", ""

    return no_update, no_update, no_update


@app.callback(Output("download-pdf-report", "data"), [Input("download-report-button", "n_clicks")],
              [State("selected-file-id-store", "data"), State("current-filters-store", "data")],
              prevent_initial_call=True)
def download_report_callback(n_clicks, file_id, filters):
    if n_clicks and file_id:
        details = db.get_log_file_details(file_id);
        filename = details['filename'] if details else "Unknown"
        report_fn = f"LogSight_Report_{filename.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        kw = filters.get("keyword");
        eid = filters.get("event_id");
        lvl = filters.get("level");
        prov = filters.get("provider")
        start = filters.get("date_start");
        end = filters.get("date_end")
        total_for_report = db.get_parsed_log_count_for_file(file_id, kw, eid, lvl, prov, start, end)

        REPORT_LOG_LIMIT = 500
        # Ensure page_size for fetching all logs is at least 1 if total_for_report > 0
        fetch_page_size = min(total_for_report, REPORT_LOG_LIMIT) if total_for_report > 0 else 1

        logs_for_report_df = db.get_parsed_logs_for_file(file_id, 1, fetch_page_size, kw, eid, lvl, prov, start, end)

        ai_summary = "AI summary could not be generated for this selection."
        if not logs_for_report_df.empty:
            sample_summaries = "\n---\n".join(
                logs_for_report_df['raw_summary_for_llm'].dropna().head(PDF_SUMMARY_LOG_SAMPLE_SIZE).tolist())
            if sample_summaries: ai_summary = get_report_summary_llm(sample_summaries, filename)

        map_cols = {"log_id": "ID", "timestamp": "Time", "event_id": "EID", "provider": "Provider",
                    "level": "Lvl", "description": "Desc.", "llm_explanation": "LLM Notes",
                    "llm_relevance": "LLM Risk", "llm_iocs": "LLM IoCs"}
        if not logs_for_report_df.empty:
            pdf_df = logs_for_report_df[[c for c in logs_for_report_df.columns if c in map_cols]].rename(
                columns=map_cols)
        else:
            pdf_df = pd.DataFrame(columns=list(map_cols.values()))
            if not ai_summary or "Error generating AI summary" in ai_summary:
                ai_summary = "No log entries match the current filters. Therefore, no AI summary can be generated."

        pdf_bytes = pdf_generator.generate_log_analysis_pdf(pdf_df, filename, filters, ai_summary)
        return dcc.send_bytes(pdf_bytes, report_fn)
    return no_update


@app.callback(Output('current-log-page-store', 'data'), [Input('log-pagination', 'active_page')])
def store_current_log_page(page): return page if page is not None else 1


if __name__ == '__main__':
    print("Initializing LogSight Pro...")
    print("Access dashboard at http://127.0.0.1:8050/")
    app.run(debug=True, host='0.0.0.0', port=8050)