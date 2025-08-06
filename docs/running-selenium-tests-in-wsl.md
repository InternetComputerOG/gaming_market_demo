# Running Selenium Tests in Windows Subsystem for Linux (WSL)

Browser automation in WSL has inherent limitations due to the lack of a native display server. This guide explains how to run Selenium tests in WSL using VcXsrv X Server.

## Setup Instructions

### 1. Install VcXsrv X Server on Windows

1. Download VcXsrv from [SourceForge](https://sourceforge.net/projects/vcxsrv/)
2. Install the application with default settings
3. Launch XLaunch from the Start menu
   - Select "Multiple windows" and set "Display number" to `-1`
   - Select "Start no client"
   - Check "Disable access control" (important for WSL connectivity)
   - Complete the setup and launch the X Server

### 2. Configure WSL to use the X Server

Add the following to your `~/.bashrc` file in WSL:

```bash
export DISPLAY=$(grep -m 1 nameserver /etc/resolv.conf | awk '{print $2}'):0.0
```

This command automatically finds your Windows host IP address and configures the DISPLAY environment variable.

Then reload your bashrc:

```bash
source ~/.bashrc
```

### 3. Install Required Browser and WebDriver

For Chrome/Chromium:

```bash
sudo apt update
sudo apt install chromium-browser chromium-chromedriver
```

Verify installation:

```bash
which chromium-browser
which chromedriver
```

### 4. Running the Tests

With X Server running on Windows and DISPLAY environment variable set in WSL:

```bash
python app/scripts/run_demo.py
```

The test script will automatically detect the X Server and use appropriate browser settings.

## Troubleshooting

1. **"Cannot connect to X server"**:
   - Ensure VcXsrv is running on Windows
   - Verify "Disable access control" was checked during XLaunch setup
   - Confirm DISPLAY variable is set correctly: `echo $DISPLAY`
   - Check Windows Firewall settings to allow VcXsrv connections

2. **"Chrome failed to start"**:
   - Ensure chromium-browser and chromedriver versions are compatible
   - Try manually launching chromium-browser first: `chromium-browser --no-sandbox`
   
3. **Tests still fail with X Server**:
   - X forwarding in WSL can be unstable; consider running the tests directly in Windows or via Docker

## Alternative Options

If X Server in WSL is still problematic:

1. **Run directly in Windows**: Install Python, Selenium and Chrome on Windows host
2. **Use Docker**: Use a Docker container with Selenium Grid/standalone setup
3. **Remote WebDriver**: Configure Selenium to connect to a remote WebDriver instance

## Script Details

The test script (`app/AppTests/test_demo.py`) now automatically detects:
- If running in WSL environment
- If X Server is configured (DISPLAY environment variable is set)
- Provides appropriate error messages and setup instructions
- Configures Chrome with optimal settings for X Server when available

This approach balances automation needs with the technical limitations of browser testing in WSL.
