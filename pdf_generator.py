# pdf_generator.py
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.units import inch
from io import BytesIO
from datetime import datetime
import pandas as pd
import re

# --- Professional Theme Colors ---
COLOR_DARK_BLUE_GREY = colors.HexColor("#2C3E50")
COLOR_MEDIUM_GREY = colors.HexColor("#7F8C8D")
COLOR_LIGHT_GREY_TEXT = colors.HexColor("#34495E")
COLOR_WHITE_TEXT = colors.HexColor("#FFFFFF")
COLOR_TABLE_HEADER_BG = colors.HexColor("#34495E")
COLOR_TABLE_ROW_LIGHT = colors.HexColor("#F4F6F6")
COLOR_TABLE_ROW_DARK = colors.HexColor("#EAECEE")
COLOR_ACCENT_PURPLE = colors.HexColor("#8E44AD")
COLOR_TABLE_GRID = colors.HexColor("#D5DBDB")


def _header_footer_enhanced(canvas, doc):
    canvas.saveState()
    header_footer_style = ParagraphStyle('HeaderFooterStyle', fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    page_num_text = f"Page {canvas.getPageNumber()}"
    p_footer = Paragraph(page_num_text, header_footer_style)
    p_footer.wrapOn(canvas, doc.width, doc.bottomMargin)
    p_footer.drawOn(canvas, doc.leftMargin, 0.3 * inch)
    canvas.setStrokeColor(colors.lightgrey)
    canvas.line(doc.leftMargin, 0.5 * inch, doc.width + doc.leftMargin, 0.5 * inch)
    canvas.restoreState()


def convert_backticks_to_font_tags(text_segment):
    """
    Converts text enclosed in backticks (`) to <font name='Courier'>...</font> tags.
    Handles multiple occurrences in a line.
    """
    if text_segment is None:  # Handle None input
        return ""
    
    return re.sub(r'`(.*?)`', r"<font name='Courier'>\1</font>", str(text_segment))


def generate_log_analysis_pdf(log_data_df, filename_for_report, filters_applied,
                              ai_summary_text="AI summary not generated."):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                            rightMargin=0.6 * inch, leftMargin=0.6 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.8 * inch,
                            title=f"LogSight Pro Report - {filename_for_report}",
                            author="LogSight Pro Platform")

    story = []
    styles = getSampleStyleSheet()

    # --- Custom Styles ---
    style_report_title = ParagraphStyle('ReportTitle', parent=styles['h1'], fontSize=22, alignment=TA_LEFT,
                                        textColor=COLOR_DARK_BLUE_GREY, spaceAfter=10, fontName='Helvetica-Bold',
                                        leading=26)
    style_report_subtitle = ParagraphStyle('ReportSubtitle', parent=styles['h2'], fontSize=14, alignment=TA_LEFT,
                                           textColor=COLOR_DARK_BLUE_GREY, spaceBefore=6, spaceAfter=4,
                                           fontName='Helvetica-Bold', leading=18)
    style_meta_info = ParagraphStyle('MetaInfo', parent=styles['Normal'], fontSize=9, textColor=COLOR_MEDIUM_GREY,
                                     spaceAfter=16, fontName='Helvetica')
    style_section_header = ParagraphStyle('SectionHeader', parent=styles['h2'], fontSize=13,
                                          textColor=COLOR_DARK_BLUE_GREY, fontName='Helvetica-Bold', spaceBefore=18,
                                          spaceAfter=8, leading=16, borderColor=COLOR_MEDIUM_GREY,
                                          borderPadding=(2, 0, 6, 0), borderWidths=(0, 0, 0.5, 0))
    style_body_text = ParagraphStyle('BodyText', parent=styles['Normal'], fontSize=10, textColor=COLOR_LIGHT_GREY_TEXT,
                                     spaceAfter=7, leading=14, alignment=TA_JUSTIFY, fontName='Helvetica')
    style_filter_item = ParagraphStyle('FilterItem', parent=style_body_text, leftIndent=12, spaceAfter=3)
    style_small_italic = ParagraphStyle('ReportSmallItalic', parent=styles['Italic'], fontSize=8,
                                        textColor=COLOR_MEDIUM_GREY, spaceAfter=10,
                                        alignment=TA_LEFT)
    style_table_header_text = ParagraphStyle('TableHeader', parent=styles['Normal'], fontName='Helvetica-Bold',
                                             fontSize=8, textColor=COLOR_WHITE_TEXT, alignment=TA_CENTER, leading=10)
    style_table_cell_text = ParagraphStyle('TableCell', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5,
                                           textColor=COLOR_LIGHT_GREY_TEXT, leading=9, alignment=TA_LEFT)

    # --- Report Structure ---
    story.append(Paragraph("LogSight Pro", style_report_title))
    story.append(
        Paragraph(f"Log Analysis Report for: <font color='{COLOR_ACCENT_PURPLE.hexval()}'>{filename_for_report}</font>",
                  style_report_subtitle))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                           style_meta_info))

    if filters_applied:
        story.append(Paragraph("Applied Filters", style_section_header))
        filter_items_text = []
        if filters_applied.get("keyword"): filter_items_text.append(f"<b>Keyword:</b> {filters_applied['keyword']}")
        if filters_applied.get("event_id"): filter_items_text.append(f"<b>Event ID:</b> {filters_applied['event_id']}")
        if filters_applied.get("level"): filter_items_text.append(f"<b>Level:</b> {filters_applied['level']}")
        if filters_applied.get("provider"): filter_items_text.append(f"<b>Provider:</b> {filters_applied['provider']}")
        if filters_applied.get("date_start"):
            filter_items_text.append(
                f"<b>Date Range:</b> {filters_applied['date_start']} to {filters_applied.get('date_end', 'Present')}")
        if filter_items_text:
            for item_html in filter_items_text: story.append(Paragraph(item_html, style_filter_item))
        else:
            story.append(Paragraph("<i>None specific.</i>", style_filter_item))

    story.append(Paragraph("AI Executive Summary", style_section_header))
    ai_summary_content = ai_summary_text
    if not ai_summary_text or "Error" in ai_summary_text or "not initialized" in ai_summary_text or "not generated" in ai_summary_text:
        ai_summary_content = "<i>AI-generated summary could not be produced for this selection. This may be due to insufficient data or an issue with the AI service.</i>"

    summary_paragraphs = ai_summary_content.split('\n')
    for para_text in summary_paragraphs:
        if para_text.strip():
            # USE THE NEW HELPER FUNCTION
            para_text_html = convert_backticks_to_font_tags(para_text.replace("    ", "    "))
            story.append(Paragraph(para_text_html, style_body_text))

    story.append(Paragraph("Detailed Log Entries", style_section_header))
    if log_data_df.empty:
        story.append(Paragraph("<i>No log data matches the current filters.</i>", style_body_text))
    else:
        headers = log_data_df.columns.tolist()
        header_row_styled = [Paragraph(h, style_table_header_text) for h in headers]
        data_for_table = [header_row_styled]
        for _, row in log_data_df.iterrows():
            table_row_styled = []
            for col_name in headers:
                cell_value = str(row.get(col_name, ''))
                # USE THE NEW HELPER FUNCTION FOR TABLE CELLS TOO
                cell_value_html = convert_backticks_to_font_tags(cell_value)
                table_row_styled.append(Paragraph(cell_value_html, style_table_cell_text))
            data_for_table.append(table_row_styled)

        col_widths_weights = {"ID": 0.7, "Time": 2.5, "EID": 0.8, "Provider": 1.8, "Lvl": 0.8, "Desc.": 2.5,
                              "LLM Notes": 3.5, "LLM Risk": 2.5, "LLM IoCs": 2.0}
        available_width = doc.width
        current_weights = [col_widths_weights.get(h, 1.0) for h in headers]
        total_weight = sum(current_weights) if sum(current_weights) > 0 else 1
        col_widths = [(w / total_weight) * available_width for w in current_weights]

        table = Table(data_for_table, colWidths=col_widths, repeatRows=1)
        table_style_config = [
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_TABLE_HEADER_BG), ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE_TEXT),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6), ('TOPPADDING', (0, 0), (-1, 0), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 4), ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_TABLE_GRID),
            ('BOX', (0, 0), (-1, -1), 0.7, COLOR_DARK_BLUE_GREY),
        ]
        for i in range(1, len(data_for_table)):
            bg_color = COLOR_TABLE_ROW_LIGHT if i % 2 == 1 else COLOR_TABLE_ROW_DARK
            table_style_config.append(('BACKGROUND', (0, i), (-1, i), bg_color))
        table.setStyle(TableStyle(table_style_config))
        story.append(table)
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(f"Total Log Entries in Report: {len(log_data_df)}", style_small_italic))

    story.append(PageBreak())
    story.append(Paragraph("Report Notes & Disclaimers", style_section_header))
    story.append(Paragraph("This report is automatically generated based on the provided log data and AI analysis.",
                           style_body_text))
    story.append(Paragraph(
        "AI-generated content should be reviewed by a human analyst. Findings are based on the data available at the time of generation.",
        style_body_text))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("LogSight Pro - Confidential", style_small_italic))

    doc.build(story, onFirstPage=_header_footer_enhanced, onLaterPages=_header_footer_enhanced)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value
