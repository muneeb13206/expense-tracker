# Open the App on Your Phone

By default the app only runs on your own computer (`127.0.0.1`). This guide shows how to open it from your phone while both devices are on the same Wi-Fi network.

> **Security note:** this app has no login. Anyone who can reach the address can view and change your data. Only do this on a **trusted home network**, and stop the server when you are done.

## Before you start

- Install the project and activate the virtual environment (see `README.md`).
- Your phone and computer must be on the **same Wi-Fi network**.

## Step 1: Find your computer's local IP address

**Windows (Command Prompt):**

```cmd
ipconfig
```

Look for **IPv4 Address** under your Wi-Fi adapter, for example `192.168.1.15`.

**macOS:**

```bash
ipconfig getifaddr en0
```

**Linux:**

```bash
hostname -I
```

Use the first address shown, for example `192.168.1.15`.

## Step 2: Start the server so other devices can reach it

`--host=0.0.0.0` tells Flask to accept connections from other devices on your network, not just your own computer.

### Option A: Change the script

In `app.py`, change the last line to:

```python
if __name__ == "__main__":
    # Use debug=False when the app is reachable from other devices.
    create_app().run(host="0.0.0.0", port=5000, debug=False)
```

Then run:

```bash
python app.py
```

Change it back to `host="127.0.0.1"` when you are finished.

### Option B: Use the terminal (no code change)

If you run Flask using the terminal command instead of editing your script:

**Linux / macOS:**

```bash
export FLASK_APP=app.py
flask run --host=0.0.0.0 --port=5000
```

**Windows (Command Prompt):**

```cmd
set FLASK_APP=app.py
flask run --host=0.0.0.0 --port=5000
```

If `flask` is not recognized on Windows, use this instead:

```cmd
python -m flask --app app run --host=0.0.0.0 --port=5000
```

Do **not** add `--debug` here. Debug mode exposes a developer console that must never be reachable from other devices.

The first time you run it on Windows, a firewall prompt may appear. Choose **Private networks** and click **Allow access**.

## Step 3: Open the app on your phone

1. Open your mobile browser (Safari, Chrome, etc.).
2. Type your computer's local IP address followed by the port number:

```text
http://192.168.1.15:5000
```

Replace `192.168.1.15` with your actual IP address from Step 1, and `5000` with your port if you changed it.

## Troubleshooting

### Connection timed out or refused

- **Check your firewall settings.** On Windows or Mac, the firewall might be blocking incoming traffic on port 5000. Allow Python on private networks.
- **Verify that both devices are on the exact same Wi-Fi network.** Guest networks, or routers with client isolation enabled, block devices from talking to each other.
- **Check the address.** It must start with `http://` (not `https://`) and include `:5000`.
- **Confirm the server is running.** The terminal should show `Running on http://0.0.0.0:5000`.

### The page loads but has no icons

The icons come from Font Awesome over the internet. Your phone needs internet access (Wi-Fi with internet is fine).

## Alternative: access from outside your home (ngrok)

If you need to reach the app over mobile data, or from another network, use a tunneling service such as [ngrok](https://ngrok.com):

```bash
ngrok http 5000
```

ngrok prints a public `https://...` address that forwards to your computer. You will need a free ngrok account and its auth token (`ngrok config add-authtoken YOUR_TOKEN`).

> **Warning:** a tunnel makes the app reachable by **anyone on the internet who has the link**, and this app has no login. Do not use it with real financial data. If you try it, load the **sample data** only, and close ngrok as soon as you are done.

## When you are finished

Press **Ctrl + C** in the terminal to stop the server. If you edited `app.py` (Option A), set `host` back to `"127.0.0.1"` and `debug=True` for local development.
