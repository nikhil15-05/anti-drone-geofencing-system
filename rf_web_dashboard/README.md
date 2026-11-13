# Dashboard runbook

The full project architecture, model/training details, data format, and API
documentation are in the [repository README](../README.md). This page contains
the dashboard setup and everyday run commands.

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer and npm
- The trained model at `Models_and_Dataset/Models/rf_drone_model.pkl`
- A serial device that outputs one 125-bit binary frame per line for live data

## First-time setup

From the repository root, create the backend environment and install Python
dependencies:

```powershell
Set-Location .\rf_web_dashboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

In a second terminal, install frontend dependencies:

```powershell
Set-Location .\rf_web_dashboard\frontend
npm install
```

Install dependencies again only when the corresponding requirements or package
manifest changes.

## Start the dashboard next time

Open the repository in VS Code and open two terminals at the repository root.
Find the connected device's serial port with:

```powershell
python -m serial.tools.list_ports -v
```

**Terminal 1 — FastAPI backend**

```powershell
Set-Location .\rf_web_dashboard
.\.venv\Scripts\Activate.ps1
$env:SERIAL_PORT = "YOUR_SERIAL_PORT"
python app.py
```

Replace `YOUR_SERIAL_PORT` with your device's serial port. Keep this terminal
running.

**Terminal 2 — React frontend**

```powershell
Set-Location .\rf_web_dashboard\frontend
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`. Keep both
terminals running while using the dashboard. If a terminal is already in
`rf_web_dashboard`, skip that folder's `Set-Location` command; for the frontend
use `Set-Location .\frontend`.

The backend can start without `SERIAL_PORT`, but it will not receive live
frames. The baud rate defaults to `115200` and can be changed by setting
`BAUD_RATE` in the backend terminal.

The current positive-class training data uses a 2.4 GHz RC car/controller as a
proxy target. A positive dashboard result means the scan resembles the learned
target-source data; it does not prove that a drone is present. See the root
README for dataset labeling and evaluation guidance.

## Production build

Build the React frontend from the repository root:

```powershell
Set-Location .\rf_web_dashboard\frontend
npm run build
```

Start FastAPI from the repository root:

```powershell
Set-Location .\rf_web_dashboard
.\.venv\Scripts\Activate.ps1
$env:SERIAL_PORT = "YOUR_SERIAL_PORT"
python app.py
```

Open `http://localhost:5000`. FastAPI serves the built frontend from
`frontend/dist` and exposes `GET /api/health`, WebSocket `/ws`, and interactive
API documentation at `/docs`.

Run a single backend process because it owns the serial device. See the root
README's [troubleshooting section](../README.md#troubleshooting) if the model,
serial connection, or UI does not start as expected.
