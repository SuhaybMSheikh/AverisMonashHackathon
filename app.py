#!/usr/bin/env python3
"""
Web server for SDOC Hackathon submission.
Provides /health endpoint and email processing API.
"""
from flask import Flask, jsonify, request
from loader import Inbox
import os

app = Flask(__name__)

# Initialize inbox
inbox = Inbox(".")

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    try:
        emails = inbox.emails()
        return jsonify({
            "status": "healthy",
            "message": "Server is running",
            "emails_loaded": len(emails)
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "message": str(e)
        }), 500

@app.route('/emails', methods=['GET'])
def get_emails():
    """List all emails."""
    try:
        emails = inbox.emails()
        return jsonify({
            "count": len(emails),
            "emails": [{"email_id": e["email_id"], "subject": e.get("subject", "")} for e in emails]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/emails/<email_id>', methods=['GET'])
def get_email(email_id):
    """Get a specific email."""
    try:
        email = inbox.get(email_id)
        return jsonify(email), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@app.route('/attachments/<path:att_path>', methods=['GET'])
def get_attachment(att_path):
    """Get attachment text content."""
    try:
        text = inbox.read_text(f"attachments/{att_path}")
        return text, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as e:
        return jsonify({"error": str(e)}), 404

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='127.0.0.1', port=port, debug=True)
