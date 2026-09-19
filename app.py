#!/usr/bin/env python3
import os

from backend.app.main import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
