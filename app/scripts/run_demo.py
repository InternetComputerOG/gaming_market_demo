# run_demo.py
import os
import signal
import subprocess
import time
import psutil

def kill_streamlit_and_chrome_processes():
    """Kill any running Streamlit and Chrome processes and associated background tasks."""
    killed_count = 0
    
    # Kill streamlit and chrome processes using psutil
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.cmdline()
            if cmdline and (any('streamlit' in arg.lower() for arg in cmdline) or 
                           any('chrome' in arg.lower() for arg in cmdline) or
                           any('chromedriver' in arg.lower() for arg in cmdline)):
                print(f"Killing process PID {proc.pid}: {' '.join(cmdline)}")
                proc.terminate()
                try:
                    proc.wait(timeout=3)  # Wait for graceful shutdown
                    killed_count += 1
                except psutil.TimeoutExpired:
                    print(f"Process {proc.pid} didn't terminate gracefully, force killing...")
                    proc.kill()
                    killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except Exception as e:
            print(f"Error killing process: {e}")
    
    # Also try pkill as a backup
    try:
        result = subprocess.run(['pkill', '-f', 'streamlit'], capture_output=True, text=True)
        if result.returncode == 0:
            print("Additional streamlit processes killed with pkill")
    except Exception as e:
        print(f"pkill failed: {e}")
    
    if killed_count > 0:
        print(f"Killed {killed_count} Streamlit processes")
        time.sleep(2)  # Give time for ports to be released
    else:
        print("No running Streamlit processes found")

if __name__ == "__main__":
    # Step 1: Halt any running Streamlit applications and background processes
    print("Halting any existing Streamlit and Chrome processes...")
    kill_streamlit_and_chrome_processes()
    time.sleep(2)  # Brief pause to ensure processes are terminated

    # Step 2: Start the admin Streamlit app on port 8502
    print("Starting admin Streamlit app on port 8502...")
    # Change to project root directory to fix module imports
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    print(f"Project root: {project_root}")
    
    # Set up environment with explicit PYTHONPATH
    env = os.environ.copy()
    env['PYTHONPATH'] = project_root
    print(f"PYTHONPATH set to: {env['PYTHONPATH']}")

    # Start admin Streamlit app on port 8503
    print("Starting admin Streamlit app on port 8503...")
    admin_process = subprocess.Popen(
        ["streamlit", "run", "app/streamlit_admin.py", "--server.port=8503"],
        cwd=project_root,
        env=env
    )

    # Start user Streamlit app for Tester1 on port 8501
    print("Starting user Streamlit app for Tester1 on port 8501...")
    user1_process = subprocess.Popen(
        ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501"],
        cwd=project_root,
        env=env
    )

    # Start user Streamlit app for Tester2 on port 8502
    print("Starting user Streamlit app for Tester2 on port 8502...")
    user2_process = subprocess.Popen(
        ["streamlit", "run", "app/streamlit_app.py", "--server.port=8502"],
        cwd=project_root,
        env=env
    )

    # Wait for apps to start up and check if they're running
    print("Waiting for Streamlit apps to start...")
    time.sleep(5)
    
    # Check if processes are still running
    if admin_process.poll() is not None:
        print(f"ERROR: Admin Streamlit process exited with code {admin_process.returncode}")
        print("Exiting due to admin process failure.")
        exit(1)
    
    if user1_process.poll() is not None:
        print(f"ERROR: User1 Streamlit process exited with code {user1_process.returncode}")
        print("Exiting due to user1 process failure.")
        exit(1)
        
    if user2_process.poll() is not None:
        print(f"ERROR: User2 Streamlit process exited with code {user2_process.returncode}")
        print("Exiting due to user2 process failure.")
        exit(1)
        
    print("All three Streamlit apps appear to be running. Waiting additional time for full startup...")
    time.sleep(5)

    # Step 3: Trigger the AppTest file (run the test script)
    print("Running AppTest...")
    test_result = subprocess.call(["python", "app/AppTests/test_demo.py"], cwd=project_root)

    if test_result == 0:
        print("AppTest completed successfully.")
    else:
        print(f"AppTest failed with exit code {test_result}.")

    # Optionally, keep the processes running or kill them after test
    # For now, let them run; user can Ctrl+C to stop
    try:
        admin_process.wait()
        app_process.wait()
    except KeyboardInterrupt:
        print("Shutting down...")
        admin_process.terminate()
        app_process.terminate()
        kill_streamlit_processes()