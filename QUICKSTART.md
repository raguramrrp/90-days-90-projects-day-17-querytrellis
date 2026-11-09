# Quickstart Guide — QueryTrellis (Windows)

Get **QueryTrellis** running locally on Windows in under 3 minutes.

## Option A: One-Command Batch Setup

```powershell
git clone <your-repo-url>
cd 90-days-90-projects-day-17-querytrellis
.\setup.bat
```

Edit `.env` to set your PostgreSQL password (`PGPASSWORD=...`) if your local PostgreSQL server requires password authentication, then seed the sample database and start the workbench:

```powershell
.\.venv\Scripts\python.exe scripts\setup_sample_db.py
.\run.bat
```

Open `http://127.0.0.1:8501` in your browser.

## Option B: Manual Windows PowerShell Setup

```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Configure environment variables
Copy-Item .env.example .env
# Edit .env and set PGPASSWORD if required by your PostgreSQL server

# 4. Create & populate the 281,525-row sample e-commerce database
python scripts\setup_sample_db.py

# 5. Launch QueryTrellis Streamlit Workbench
streamlit run app/main.py --server.address 127.0.0.1 --server.port 8501
```

## Option C: Isolated Local PostgreSQL Cluster (No System Service Changes)

If PostgreSQL binaries (`initdb`, `pg_ctl`) are installed and you prefer a self-contained project cluster on `127.0.0.1:55432`:

```powershell
.\.venv\Scripts\python.exe scripts\local_pg_cluster.py start --port 55432
.\.venv\Scripts\python.exe scripts\setup_sample_db.py --host 127.0.0.1 --port 55432 --user postgres
```

Then connect inside QueryTrellis **Settings** (`Host: 127.0.0.1`, `Port: 55432`, `Database: querytrellis_sample`, `Username: postgres`, empty password). When finished:

```powershell
.\.venv\Scripts\python.exe scripts\local_pg_cluster.py stop
```

## Run Automated Tests

```powershell
.\test.bat
```
