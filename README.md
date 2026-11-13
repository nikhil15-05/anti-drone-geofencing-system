# RF Sentinel

RF Sentinel is a research prototype that reads 125-channel radio-frequency
scan frames from a serial device, classifies them with a Random Forest model,
and displays live channel activity in a browser dashboard.

> **Important:** this is not a validated drone detector or a flight-safety
> system. The current positive-class data includes a 2.4 GHz RC car/controller
> used as a proxy RF source. A positive result means a frame resembles the
> model's training data; it does not identify a drone.

## Run from GitHub with Codespaces

You can start the software in a cloud development environment without
downloading the project or opening a local project folder:

1. Open this repository on GitHub.
2. Select **Code → Codespaces → Create codespace on main**.
3. In the Codespace terminal, install the backend dependencies and start the
   backend:

   ```bash
   cd rf_web_dashboard
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python app.py
   ```

4. Open a second terminal and start the frontend:

   ```bash
   cd rf_web_dashboard/frontend
   npm ci
   npm run dev -- --host 0.0.0.0
   ```

5. Open the forwarded port **5173** from the Codespaces **Ports** tab. Vite
   proxies API requests and the WebSocket stream to the backend on port 5000.

The Codespace can run the web app, but it normally cannot access a USB/serial
device physically connected to your computer. Without a serial device
accessible to the backend, the dashboard opens but has no live frames.
GitHub Pages hosts static files and GitHub Actions runs finite jobs; neither
provides a persistent backend connected to your local serial device. To use
live hardware remotely, run the backend on a computer that can access that
device and provide a network connection to the frontend.

## Download and run locally

Download the repository as a ZIP from **Code → Download ZIP**, extract it, and
open a terminal in the extracted project. Python 3.10 or newer, Node.js 18 or
newer, and npm are required.

### Windows PowerShell

In the first terminal, install and start the backend:

```powershell
Set-Location .\rf_web_dashboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SERIAL_PORT = "YOUR_SERIAL_PORT"
python app.py
```

Replace `YOUR_SERIAL_PORT` with the port assigned to your device. To find
available serial ports, run `python -m serial.tools.list_ports -v` in an
activated environment.

In a second terminal, install and start the frontend:

```powershell
Set-Location .\rf_web_dashboard\frontend
npm ci
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`. Keep both
terminals running. If you do not have a serial device, omit the
`SERIAL_PORT` assignment; the interface can still open, but it will not
receive live frames.

### macOS or Linux

In the first terminal:

```bash
cd rf_web_dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SERIAL_PORT=YOUR_SERIAL_PORT
python app.py
```

Replace `YOUR_SERIAL_PORT` with the serial device path for your system. In a
second terminal:

```bash
cd rf_web_dashboard/frontend
npm ci
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`.

### Serve a production frontend locally

Build the frontend, then run FastAPI. From the project root:

```bash
cd rf_web_dashboard/frontend
npm ci
npm run build
cd ..
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SERIAL_PORT=YOUR_SERIAL_PORT
python app.py
```

Replace `YOUR_SERIAL_PORT` with the port for your device, or omit the `export`
line if no serial device is available. On Windows, activate the
environment with `.\.venv\Scripts\Activate.ps1` and set the port with
`$env:SERIAL_PORT = "YOUR_SERIAL_PORT"`. Open `http://localhost:5000`.

## Hardware and components

The software does not specify or include a particular RF scanner design. To
use live input, you need:

- An RF scanning device and suitable antenna that can produce the project's
  125-channel scan data. The device firmware must output one frame per line.
- A compatible USB serial connection (or a UART-to-USB adapter), with power
  and data connections appropriate for the device.
- A computer that can access the serial device and run Python. The dashboard
  frontend additionally requires Node.js and npm for development/build.
- A browser with network access to the running dashboard.

Connect the scanner to the computer, identify its serial port, and set the
`SERIAL_PORT` environment variable in the terminal that starts the backend.
The default serial speed is **115200 baud**; set `BAUD_RATE` if the device
uses a different speed. The backend accepts only newline-terminated frames
that contain exactly 125 characters, each either `0` or `1`. Confirm that
your scanner and firmware produce this format before connecting it.

Use RF equipment only where permitted and follow applicable radio regulations.
Do not treat model output as evidence of a particular transmitter or as a
replacement for validated measurement equipment.

## Collect data and train the model

The serial data collector records labeled frames to
`Models_and_Dataset/Datasets/`. From the project root, activate an environment
with the backend requirements installed and run:

```bash
python Collecting_Dataset/collect_data.py
```

Set `SERIAL_PORT` before running the collector. It offers background,
target-source, Wi-Fi-stress, and custom recording options. The collector's
serial speed is currently fixed at 115200 baud. New recordings are written as
CSV files and should be reviewed to ensure their labels match the recorded
conditions.

Train and evaluate the classifier from the project root:

```bash
python Models_and_Dataset/train_model.py
```

The training program validates CSV columns and binary labels, computes
temporal features per recording, evaluates with a recording-grouped holdout,
then fits the final model on all recordings. It saves the model to
`Models_and_Dataset/Models/rf_drone_model.pkl`. The grouped evaluation needs
multiple independent recordings for both labels. The dashboard requires this
model file; retrain it if it is missing.

## Data format and classifier

Each dataset CSV contains 125 channel columns (`ch_0` through `ch_124`) and a
binary `label` column. A live serial frame contains the 125 channel values as
a single string of binary digits.

The model uses the latest frame's 125 values plus four derived features:
active-channel count, activity from channel 31 onward, change from the
previous frame, and the spread of active channel indices. It waits for five
frames to build a feature window. The dashboard smooths predictions over 15
frames and raises its target-source indication when at least 30% of those
predictions are positive.

The provided model is a Python pickle-based artifact. Only load model files
from this project or another source you trust; loading an untrusted pickle can
execute code.

## API

- `GET /api/health` reports whether the model loaded, whether serial is
  connected, and the latest frame sequence.
- `WS /ws` streams validated frames and their classification results.
- `GET /docs` serves FastAPI's interactive API documentation.

The frontend development server proxies `/api` and `/ws` to the backend.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `SERIAL_PORT` | Unset | Serial device port/path; required for live frames |
| `BAUD_RATE` | `115200` | Serial connection speed |
| `LOG_LEVEL` | `INFO` | Python logging level |

Set configuration in the terminal that starts the backend. Do not put
machine-specific serial settings, credentials, or private keys in source
files or commit them to the repository.

## Repository layout

```text
Collecting_Dataset/          Serial-to-CSV data collector
Models_and_Dataset/
  Datasets/                  Example labeled recordings
  Models/                    Trained model artifact
  train_model.py             Training and evaluation
rf_web_dashboard/
  app.py                     FastAPI backend and serial reader
  requirements.txt           Python dependencies
  frontend/                  React and Vite application
```

## Troubleshooting

- **Serial connection fails:** verify the port, baud rate, device permissions,
  cable, and that no other program is using the serial device.
- **No live frames:** check that the backend is running, the device sends
  newline-terminated 125-bit frames, and `SERIAL_PORT` is set in the backend
  terminal.
- **Model unavailable:** verify
  `Models_and_Dataset/Models/rf_drone_model.pkl` exists and train it if
  necessary.
- **Frontend cannot reach the backend:** run the backend on port 5000 and
  access the frontend through the Vite URL or the built app through port 5000.
- **Codespaces shows an offline/standby dashboard:** a Codespace generally
  cannot access a serial device plugged into your local computer; use a
  hardware-connected host for live data.
