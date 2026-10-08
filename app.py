import streamlit as st
import io
import re
from reportlab.lib.pagesizes import A4
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, KeepTogether, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

# --- 1. ANALYSIS ENGINE ---
def analyze_lines(lines):
    errors = []
    seen = set()
    duplicates = 0
    formatting_issues = 0
    
    current_q = None
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if re.match(r'^[a-z]\)', line): 
            formatting_issues += 1
            
        if line.upper().startswith("ANSWER:"):
            if not line.startswith("ANSWER: "): 
                formatting_issues += 1
            if current_q:
                if current_q in seen:
                    duplicates += 1
                else:
                    seen.add(current_q)
                current_q = None
        elif not re.match(r'^[A-Za-z]\)', line):
            if current_q is None:
                current_q = line

    if duplicates > 0:
        errors.append(f"Duplicates: Found {duplicates} identical duplicate question(s).")
    if formatting_issues > 0:
        errors.append(f"Formatting: Found {formatting_issues} spacing/case issue(s) (e.g., 'ANSWER:A' or 'a)').")
        
    return errors

# --- 2. PARSER & AUTO-FIXER ---
def get_questions(lines, apply_fixes=False):
    questions = []
    current_q = None
    seen_questions = set()
    
    for line in lines:
        line = line.strip()
        if not line: continue
            
        if apply_fixes:
            if line.upper().startswith("ANSWER:") and not line.upper().startswith("ANSWER: "):
                line = "ANSWER: " + line[7:].strip()
            if re.match(r'^[a-z]\)', line):
                line = line[0].upper() + line[1:]
                
        if re.match(r'^[A-F]\)', line):
            if current_q is not None:
                current_q['options'].append(line)
        elif line.startswith('ANSWER:'):
            if current_q is not None:
                current_q['answer'] = line
                if apply_fixes:
                    if current_q['question'] not in seen_questions:
                        questions.append(current_q)
                        seen_questions.add(current_q['question'])
                else:
                    questions.append(current_q)
                current_q = None
        else:
            if current_q is None:
                current_q = {'question': line, 'options': [], 'answer': ''}
            else:
                current_q['question'] += ' ' + line
                
    return questions

# --- 3. PDF GENERATOR ---
def create_two_column_pdf(questions, header_text):
    pdf_buffer = io.BytesIO()
    doc = BaseDocTemplate(
        pdf_buffer, pagesize=A4, rightMargin=10*mm, leftMargin=10*mm, topMargin=22*mm, bottomMargin=12*mm
    )
    
    frame_width = (doc.width - 10*mm) / 2
    frame_height = doc.height
    
    left_frame = Frame(doc.leftMargin, doc.bottomMargin, frame_width, frame_height, id='col1')
    right_frame = Frame(doc.leftMargin + frame_width + 10*mm, doc.bottomMargin, frame_width, frame_height, id='col2')
    
    def add_bg_and_header(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor('#faf8f5'))
        canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
        canvas.setFillColor(HexColor('#2c3e50'))
        canvas.setFont('Helvetica-Bold', 16)
        canvas.drawCentredString(doc.pagesize[0] / 2.0, doc.pagesize[1] - 15*mm, header_text)
        canvas.setStrokeColor(HexColor('#34495e'))
        canvas.setLineWidth(1.5)
        canvas.line(doc.leftMargin, doc.pagesize[1] - 18*mm, doc.pagesize[0] - doc.rightMargin, doc.pagesize[1] - 18*mm)
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id='two_columns', frames=[left_frame, right_frame], onPage=add_bg_and_header)])
    
    styles = getSampleStyleSheet()
    q_style = ParagraphStyle(name='Question', parent=styles['Normal'], fontName='Helvetica-Bold', spaceBottom=6, fontSize=9.5, leading=12, textColor=HexColor('#2b2b2b'))
    opt_style = ParagraphStyle(name='Option', parent=styles['Normal'], fontName='Helvetica', leftIndent=10, spaceBottom=3, fontSize=9.5, leading=12, textColor=HexColor('#2b2b2b'))
    ans_style = ParagraphStyle(name='Answer', parent=styles['Normal'], fontName='Helvetica-Bold', textColor=HexColor('#27ae60'), spaceBottom=0, spaceTop=6, fontSize=9.5)
    
    story = []
    for i, q in enumerate(questions, 1):
        cell_content = [Paragraph(f"{i}. {q['question']}", q_style)]
        for opt in q['options']:
            cell_content.append(Paragraph(opt, opt_style))
        cell_content.append(Paragraph(q['answer'], ans_style))
        
        card_table = Table([[cell_content]], colWidths=[frame_width])
        card_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), HexColor('#ffffff')),
            ('BOX', (0,0), (-1,-1), 1, HexColor('#eaeaea')),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        
        story.append(KeepTogether(card_table))
        story.append(Spacer(1, 10))
        
    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer

# --- 4. STREAMLIT UI ---
st.set_page_config(page_title="Aiken to PDF Converter", layout="centered")

st.title("📄 Aiken to PDF Converter")
st.markdown("Upload your Aiken-formatted text file to generate a premium two-column PDF.")

header_text = st.text_input("Document Header/Title:", "Network Lab Questions")
uploaded_file = st.file_uploader("Upload Aiken Text File", type=["txt"])

if uploaded_file is not None:
    # Handle Decoding
    bytes_data = uploaded_file.getvalue()
    try:
        text_data = bytes_data.decode("utf-8")
        encoding_issue = False
    except UnicodeDecodeError:
        text_data = bytes_data.decode("cp1252", errors="replace")
        encoding_issue = True

    lines = text_data.split('\n')
    
    # Analyze
    errors = analyze_lines(lines)
    if encoding_issue:
        errors.insert(0, "Encoding: Detected non-UTF-8 characters. Attempted auto-recovery.")

    apply_fixes = False
    if errors:
        st.warning("⚠️ **Issues Detected in File:**")
        for e in errors:
            st.markdown(f"- {e}")
        apply_fixes = st.checkbox("🛠️ Auto-correct these issues before generating?", value=True)

    if st.button("Generate PDF"):
        with st.spinner("Building PDF..."):
            questions = get_questions(lines, apply_fixes=apply_fixes)
            
            if not questions:
                st.error("No valid questions were found in the file.")
            else:
                pdf_buffer = create_two_column_pdf(questions, header_text)
                
                st.success("PDF successfully generated!")
                st.download_button(
                    label="⬇️ Download PDF",
                    data=pdf_buffer,
                    file_name="Converted_Questions.pdf",
                    mime="application/pdf"
                )
