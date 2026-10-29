# Personal Expense Tracker and Budget Analyzer

A Flask + SQLite web app to track income and expenses.

## Requirements
- Python 3.10 or newer

## Setup

### Windows
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python app.py

### macOS / Linux
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python app.py

Open http://127.0.0.1:5000

## Demo data

### Windows
    python -m flask --app app seed-sample
    python -m flask --app app clear-sample

### macOS / Linux
    python3 -m flask --app app seed-sample
    python3 -m flask --app app clear-sample

`clear-sample` removes only the demo data. Your real transactions are never touched.

## Run tests

### Windows
    python -m unittest discover -v

### macOS / Linux
    python3 -m unittest discover -v

## To run on mobile
- Make sure your laptop and phone are connected to the same WI-FI 
-on cmd, look for IPv4 Address   

    ipconfig
    export FLASK_APP=app.py
    flask run --host=0.0.0.0 --port=5000

## Notes
- Activate the virtual environment every time you open a new terminal.
- On macOS/Linux, if `python3` is not found, install Python from python.org or with your package manager (for example `brew install python` or `sudo apt install python3 python3-venv`).
- The database and secret key are created automatically in the `instance/` folder on first run. They are not stored in GitHub.