import os
import uuid
import tempfile
from flask import Flask, request, jsonify, send_from_directory, make_response
from fpdf import FPDF, XPos, YPos
from PIL import Image

app = Flask(__name__)

# --- Configuration ---
# Render free tier often uses an ephemeral filesystem, so we use a temporary directory
# for storage and serve files from a static path. Render should serve the 'static' folder.
CERT_DIR = os.path.join("static", "certificates")
BG_IMAGE_PATH = "certificate_bg.png"

# Ensure the static/certificates directory exists
os.makedirs(CERT_DIR, exist_ok=True)

class CertificatePDF(FPDF):
    """Custom PDF class to handle the certificate layout."""

    def __init__(self, bg_image_path, orientation='L', unit='mm', format='A4'):
        # A4 Landscape: 297mm x 210mm
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.bg_image_path = bg_image_path
        self.set_auto_page_break(auto=False, margin=0)
        self.add_page()
        self.draw_background()

    def draw_background(self):
        """Adds the background image to cover the entire page."""
        try:
            # Add the background image to fill the entire A4 Landscape page (297x210)
            self.image(self.bg_image_path, x=0, y=0, w=297, h=210)
        except Exception as e:
            # Fallback if image path is incorrect or file is missing
            self.set_fill_color(240, 240, 240)
            self.rect(0, 0, 297, 210, 'F')
            self.set_text_color(255, 0, 0)
            self.set_font('Arial', 'B', 48)
            self.set_xy(50, 100)
            self.cell(0, 10, "IMAGE NOT FOUND - CHECK PATH", 0, 1, 'C')
            print(f"Error loading background image: {e}")
            self.set_text_color(0, 0, 0) # Reset color

    def add_user_data(self, user_name, course_name, date_range, issue_date):
        """Adds all dynamic text to the certificate."""
        
        # --- 1. User Name (Underlined and Italic) ---
        self.set_font('Arial', 'I', 36) # Italic, Large font
        # The user name is typically centered on the certificate
        
        # To center the text, we need its width first
        name_width = self.get_string_width(user_name)
        page_center = 297 / 2 # Center of A4 Landscape is 148.5mm
        x_center = page_center - (name_width / 2)
        y_name = 110 # Estimated Y position for the name

        self.set_xy(x_center, y_name)
        self.write(10, user_name) # Write the text with a line height of 10

        # Draw the underline
        # Underline starts at x_center and ends at x_center + name_width
        # Position the line slightly below the text baseline (e.g., + 10mm from set_xy y)
        underline_y = y_name + 10 
        self.set_line_width(0.7)
        self.line(x_center, underline_y, x_center + name_width, underline_y)
        
        # --- 2. Course Name & Date Range ---
        self.set_font('Arial', '', 18) # Regular font
        y_course = 135 # Estimated Y position for course details

        # Assume a standard paragraph structure for the main body text
        main_text = (
            f"for successfully completing the **{course_name}** course,"
            f" which ran from {date_range}."
        )
        
        # Split the text to handle formatting (fpdf2 is not markdown-friendly)
        # We will keep it simple and centered, placing it slightly below the name
        self.set_xy(50, y_course)
        self.multi_cell(197, 8, main_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        # --- 3. Issue Date ---
        self.set_font('Arial', '', 14)
        y_issue = 175 # Estimated Y position near the bottom signature line
        
        self.set_xy(200, y_issue)
        self.cell(0, 10, f"Date Issued: {issue_date}", 0, 1, 'L')


@app.route('/generate-certificate', methods=['POST'])
def generate_certificate():
    """Endpoint to accept data and generate the PDF certificate."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        user_name = data.get("userName")
        course_name = data.get("courseName")
        date_range = data.get("dateRange")
        issue_date = data.get("issueDate")

        if not all([user_name, course_name, date_range, issue_date]):
            return jsonify({"error": "Missing required fields (userName, courseName, dateRange, issueDate)"}), 400

        # Generate unique filename
        filename = f"certificate_{uuid.uuid4()}.pdf"
        filepath = os.path.join(CERT_DIR, filename)

        # 1. Generate PDF
        pdf = CertificatePDF(BG_IMAGE_PATH)
        pdf.add_user_data(user_name, course_name, date_range, issue_date)
        
        # 2. Save PDF to the static directory
        pdf.output(filepath, 'F')

        # 3. Construct the public URL
        # Render free tier apps are typically hosted at <app-name>.onrender.com
        # The URL must be absolute for external access (like from Flutter)
        # In a real deployment, you must set the BASE_URL environment variable 
        # to your Render URL (e.g., https://my-cert-backend.onrender.com)
        # For local testing, this will be http://127.0.0.1:5000/static/certificates/<filename>
        
        base_url = os.environ.get("BASE_URL", request.url_root)
        download_url = f"{base_url}static/certificates/{filename}"

        return jsonify({
            "status": "success",
            "message": "Certificate generated successfully.",
            "downloadUrl": download_url
        }), 200

    except Exception as e:
        app.logger.error(f"Certificate generation failed: {e}")
        return jsonify({"error": "Internal server error during PDF generation"}), 500

# Optional: Serve the static files directly. Flask does this automatically if 
# the static folder is configured, but this explicit route can be a backup.
@app.route('/static/certificates/<path:filename>')
def download_file(filename):
    return send_from_directory(
        os.path.join(os.getcwd(), 'static', 'certificates'), 
        filename, 
        as_attachment=False
    )

if __name__ == '__main__':
    # When deploying to Render, gunicorn/other WSGI server will run the app
    # This block is only for local development/testing
    print(f"Server is running. Cert storage: {os.path.join(os.getcwd(), CERT_DIR)}")
    app.run(debug=True)