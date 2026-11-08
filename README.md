# Run locally

The commands below are for Windows PowerShell. Run them from the project folder.

## 1. Create and activate a virtual environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

## 2. Install dependencies

```powershell
py -m pip install -r requirements.txt
```

## 3. Configure the Groq API key

Open `.env` and set `GROQ_API_KEY` to a valid Groq API key:

```text
GROQ_API_KEY=your_groq_api_key
```

Keep `.env` private; it is excluded from Git. If a key has been shared publicly,
revoke it and use a newly generated key.

## 4. Start the app

```powershell
py app.py
```

Open <http://127.0.0.1:5000> in your browser. Stop the server with `Ctrl+C`.
