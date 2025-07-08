import paramiko
import time
import re
import webbrowser
import subprocess
import threading
import queue
import psutil

# Global variables for session management
ssh_client = None
session_output_buffer = []  # Store session output for real-time display
active_shell = None  # Store active shell session
active_tunnel_process = None  # Store active tunnel process

def add_to_output_buffer(message, message_type="info"):
    """Add a message to the output buffer for real-time display."""
    global session_output_buffer
    timestamp = time.strftime("%H:%M:%S")
    session_output_buffer.append({
        "timestamp": timestamp,
        "message": message,
        "type": message_type
    })
    # Keep only last 1000 messages to prevent memory issues
    if len(session_output_buffer) > 1000:
        session_output_buffer = session_output_buffer[-1000:]

def get_output_buffer():
    """Get the current output buffer."""
    global session_output_buffer
    return session_output_buffer.copy()

def clear_output_buffer():
    """Clear the output buffer."""
    global session_output_buffer
    session_output_buffer = []

def establish_ssh_session(username, gateway):
    """Establish and store an SSH session."""
    global ssh_client
    if ssh_client is None:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=gateway, username=username)
    return ssh_client

def is_ssh_client_valid():
    """Check if the SSH client is valid and connected."""
    global ssh_client
    if ssh_client is None:
        return False
    try:
        # Test the connection by sending a simple command
        ssh_client.exec_command("echo test", timeout=5)
        return True
    except Exception:
        return False


def ensure_ssh_connection(load_config):
    """Ensure the SSH client is valid, and reconnect if necessary."""
    global ssh_client
    if not is_ssh_client_valid():
        print("SSH client is invalid. Attempting to reconnect...")
        if load_config is None:
            raise Exception("No load_config function provided. Cannot reconnect.")
        config = load_config()
        if not config:
            raise Exception("No saved login settings found. Cannot reconnect.")
        establish_ssh_session(config["username"], config["gateway"])

def close_ssh_session():
    """Close the SSH session."""
    global ssh_client
    if ssh_client:
        ssh_client.close()
        ssh_client = None


def run_command_with_paramiko(command, timeout=30, max_retries=5, load_config=None):
    """Run a command on the server using paramiko and ensure the SSH connection is valid."""
    if load_config is not None:
        ensure_ssh_connection(load_config)  # Ensure the SSH connection is valid
    
    for attempt in range(max_retries):
        try:
            stdin, stdout, stderr = ssh_client.exec_command(command, timeout=timeout)
            output = stdout.read().decode("utf-8")
            error = stderr.read().decode("utf-8")

            if error:
                print(f"Error: {error}")  # Log errors for debugging

            # Check if the table header is present
            if "#CPU" in output:
                return output

            print(f"Attempt {attempt + 1} failed. Retrying...")
            time.sleep(2)  # Wait before retrying
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed with exception: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise

    # If retries fail, return the last output (even if incomplete)
    return output

def is_float(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def parse_ai_output(ai_output):
    """Parse the output of the 'ai' command to extract server information."""
    lines = ai_output.splitlines()
    table_start = False
    servers = []

    for line in lines:
        # Skip lines until the table header is found
        if line.startswith("#CPU"):
            table_start = True
            continue
        if not table_start:
            continue

        # Skip error lines
        if "rsh: fork" in line or "Resource temporarily unavailable" in line:
            continue

        # Parse table rows
        parts = line.split()            

        if len(parts) >= 8 and is_float(parts[0]):  # Ensure the line has enough columns
            servers.append({
                "CPU_AVAIL": parts[0],
                "LOAD": parts[1],
                "CPU": parts[2],
                "HOST": parts[3],
                "CPU_TYPE": parts[4],
                "GB_AVAIL": parts[5],
                "GB_TOTAL": parts[6],
                "PROGRAM": parts[7],
                "HAS_GPU": 'X' if 'gpu' in parts[3].lower() else ' ',
                "USER": parts[8] if len(parts) > 8 else ""
            })

    return servers


def read_output_with_timeout(stdout, timeout=3, max_empty_reads=15):
    """Read output from stdout with a timeout, handling empty lines."""
    q = queue.Queue()

    def enqueue_output(out, queue):
        for line in iter(out.readline, b""):
            # Decode only if the line is a bytes object
            if isinstance(line, bytes):
                queue.put(line.decode("utf-8"))
            else:
                queue.put(line)
        out.close()
        queue.put(None)  # Sentinel value to indicate the stream is closed

    t = threading.Thread(target=enqueue_output, args=(stdout, q))
    t.daemon = True
    t.start()

    output = ""
    empty_reads = 0  # Counter for consecutive empty lines
    try:
        while True:
            line = q.get(timeout=timeout)
            if line is None:  # Sentinel value indicates the stream is closed
                break
            if line.strip() == "":  # Handle empty lines
                empty_reads += 1
                if empty_reads >= max_empty_reads:
                    break  # Exit if too many consecutive empty lines
                continue
            empty_reads = 0  # Reset counter if a non-empty line is read
            output += line
    except queue.Empty:
        pass

    return output


def connect_and_run_jupyter(best_server, env_name, dest_folder, local_port=8888):
    """Connect to the selected server, activate the environment, and start Jupyter Notebook."""
    try:
        # Create a shell session
        shell = ssh_client.invoke_shell()
        shell.settimeout(30)
        
        # Function to send command and wait for output
        def send_command_and_wait(command, wait_time=2):
            shell.send(command + '\n')
            time.sleep(wait_time)
            output = ""
            while shell.recv_ready():
                chunk = shell.recv(4096).decode('utf-8')
                output += chunk
                time.sleep(0.1)  # Small delay to collect all output
            return output

        # Wait for initial prompt
        time.sleep(2)
        initial_output = ""
        while shell.recv_ready():
            initial_output += shell.recv(4096).decode('utf-8')
        
        # Step 1: SSH into the selected server
        ssh_output = send_command_and_wait(f"ssh {best_server}", wait_time=5)
        if "Last login" not in ssh_output and "Welcome" not in ssh_output:
            raise Exception(f"Failed to connect to {best_server}. Output: {ssh_output}")
        
        # Step 2: Source bashrc and activate conda environment
        send_command_and_wait("source ~/.bashrc", wait_time=1)
        
        # Activate conda environment
        conda_output = send_command_and_wait(f"conda activate {env_name}", wait_time=3)
        
        # Verify environment activation
        env_check = send_command_and_wait("echo $CONDA_DEFAULT_ENV", wait_time=2)
        if env_name not in env_check:
            raise Exception(f"Failed to activate conda environment: {env_name}. Output: {env_check}")
        
        # Step 3: Navigate to destination folder
        cd_output = send_command_and_wait(f"cd {dest_folder}", wait_time=1)
        
        # Verify directory change
        pwd_output = send_command_and_wait("pwd", wait_time=1)
        if dest_folder not in pwd_output:
            raise Exception(f"Failed to change directory to: {dest_folder}. Current dir: {pwd_output}")
        
        # Step 4: Start Jupyter Notebook
        jupyter_output = send_command_and_wait("jupyter notebook --ip 0.0.0.0 --no-browser", wait_time=3)
        
        # Wait for Jupyter to fully start and collect output over time
        full_jupyter_output = jupyter_output
        max_wait_time = 60  # Maximum wait time in seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            time.sleep(2)  # Wait before checking for more output
            if shell.recv_ready():
                additional_output = ""
                while shell.recv_ready():
                    chunk = shell.recv(4096).decode('utf-8')
                    additional_output += chunk
                    time.sleep(0.1)
                full_jupyter_output += additional_output
                
                # Check if we have the URL with port and token
                if "http://" in full_jupyter_output and "token=" in full_jupyter_output:
                    break
        
        # Extract port and token from the output with more comprehensive patterns
        patterns = [
            r"http://.*?:(\d+)/.*?\?token=([a-f0-9]+)",
            r"http://localhost:(\d+)/.*?\?token=([a-f0-9]+)",
            r"http://[\w\-\.]+:(\d+)/\?token=([a-f0-9]+)",
            r"Or copy and paste one of these URLs:\s*http://.*?:(\d+)/.*?\?token=([a-f0-9]+)"
        ]
        
        port_match = None
        for pattern in patterns:
            port_match = re.search(pattern, full_jupyter_output, re.MULTILINE | re.DOTALL)
            if port_match:
                break
        
        if not port_match:
            raise Exception(f"Failed to parse Jupyter Notebook port and token. Output: {full_jupyter_output}")
        
        remote_port = port_match.group(1)
        token = port_match.group(2)
        
        # Step 5: Create an SSH tunnel using the gateway host
        gateway_host = ssh_client.get_transport().getpeername()[0]
        username = ssh_client.get_transport().get_username()
        
        tunnel_cmd = f"ssh -L {local_port}:{best_server}:{remote_port} -N {username}@{gateway_host}"
        
        # Start the tunnel in a separate process
        tunnel_process = subprocess.Popen(
            tunnel_cmd, 
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give some time for the tunnel to establish
        time.sleep(3)
        
        # Step 6: Open the Jupyter Notebook in the local browser
        notebook_url = f"http://localhost:{local_port}/?token={token}"
        webbrowser.open(notebook_url)
        
        return f"🟢 Jupyter Notebook started successfully! Access it at {notebook_url}"
        
    except Exception as e:
        raise Exception(f"An error occurred while starting Jupyter Notebook: {str(e)}")

def connect_and_run_jupyter_with_output(best_server, env_name, dest_folder, local_port=8888, output_callback=None):
    """Connect to the selected server, activate the environment, and start Jupyter Notebook with step-by-step output."""
    global active_shell
    
    def log_output(message, message_type="info"):
        """Helper function to log output"""
        add_to_output_buffer(message, message_type)  # Add to buffer for real-time display
        if output_callback:
            output_callback(message, message_type)
        print(f"[{message_type.upper()}] {message}")
    
    try:
        clear_output_buffer()  # Clear previous session output
        log_output("Starting Jupyter Notebook session...", "info")
        log_output(f"Target server: {best_server}", "info")
        log_output(f"Environment: {env_name}", "info")
        log_output(f"Directory: {dest_folder}", "info")
        
        # Smart port management
        log_output("Checking port availability...", "info")
        try:
            local_port = smart_port_cleanup_and_find(local_port)
        except Exception as e:
            log_output(f"Port management error: {e}", "error")
            raise Exception(f"Could not secure a port: {e}")
        
        log_output(f"Using local port: {local_port}", "success")
        
        # Create a shell session
        shell = ssh_client.invoke_shell()
        shell.settimeout(30)
        active_shell = shell  # Store for potential interaction
        
        log_output("SSH shell session created", "success")
        
        # Function to send command and wait for output
        def send_command_and_wait(command, wait_time=2, log_command=True):
            if log_command:
                log_output(f"Executing: {command}", "info")
            shell.send(command + '\n')
            time.sleep(wait_time)
            output = ""
            while shell.recv_ready():
                chunk = shell.recv(4096).decode('utf-8')
                output += chunk
                time.sleep(0.1)  # Small delay to collect all output
            return output

        # Wait for initial prompt
        time.sleep(2)
        initial_output = ""
        while shell.recv_ready():
            initial_output += shell.recv(4096).decode('utf-8')
        
        # Step 1: SSH into the selected server
        log_output("Connecting to remote server...", "info")
        ssh_output = send_command_and_wait(f"ssh {best_server}", wait_time=5)
        if "Last login" not in ssh_output and "Welcome" not in ssh_output:
            log_output(f"Connection failed: {ssh_output}", "error")
            raise Exception(f"Failed to connect to {best_server}. Output: {ssh_output}")
        
        log_output("Successfully connected to remote server", "success")
        
        # Step 2: Source bashrc and activate conda environment
        log_output("Setting up environment...", "info")
        send_command_and_wait("source ~/.bashrc", wait_time=1, log_command=False)
        
        # Activate conda environment
        log_output(f"Activating conda environment: {env_name}", "info")
        conda_output = send_command_and_wait(f"conda activate {env_name}", wait_time=3, log_command=False)
        
        # Verify environment activation
        env_check = send_command_and_wait("echo $CONDA_DEFAULT_ENV", wait_time=2, log_command=False)
        if env_name not in env_check:
            log_output(f"Environment activation failed: {env_check}", "error")
            raise Exception(f"Failed to activate conda environment: {env_name}. Output: {env_check}")
        
        log_output(f"Environment '{env_name}' activated successfully", "success")
        
        # Step 3: Navigate to destination folder
        log_output(f"Navigating to directory: {dest_folder}", "info")
        cd_output = send_command_and_wait(f"cd {dest_folder}", wait_time=1, log_command=False)
        
        # Verify directory change
        pwd_output = send_command_and_wait("pwd", wait_time=1, log_command=False)
        if dest_folder not in pwd_output:
            log_output(f"Directory change failed. Current: {pwd_output}", "error")
            raise Exception(f"Failed to change directory to: {dest_folder}. Current dir: {pwd_output}")
        
        log_output(f"Successfully changed to directory: {dest_folder}", "success")
        
        # Step 4: Start Jupyter Notebook
        log_output("Starting Jupyter Notebook...", "info")
        jupyter_output = send_command_and_wait("jupyter notebook --ip 0.0.0.0 --no-browser", wait_time=3, log_command=False)
        
        log_output("Waiting for Jupyter to initialize...", "info")
        
        # Wait for Jupyter to fully start and collect output over time
        full_jupyter_output = jupyter_output
        max_wait_time = 60  # Maximum wait time in seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            time.sleep(2)  # Wait before checking for more output
            if shell.recv_ready():
                additional_output = ""
                while shell.recv_ready():
                    chunk = shell.recv(4096).decode('utf-8')
                    additional_output += chunk
                    time.sleep(0.1)
                full_jupyter_output += additional_output
                
                # Check if we have the URL with port and token
                if "http://" in full_jupyter_output and "token=" in full_jupyter_output:
                    log_output("Jupyter Notebook URL detected!", "success")
                    break
        
        # Extract port and token from the output with more comprehensive patterns
        patterns = [
            r"http://.*?:(\d+)/.*?\?token=([a-f0-9]+)",
            r"http://localhost:(\d+)/.*?\?token=([a-f0-9]+)",
            r"http://[\w\-\.]+:(\d+)/\?token=([a-f0-9]+)",
            r"Or copy and paste one of these URLs:\s*http://.*?:(\d+)/.*?\?token=([a-f0-9]+)"
        ]
        
        port_match = None
        for pattern in patterns:
            port_match = re.search(pattern, full_jupyter_output, re.MULTILINE | re.DOTALL)
            if port_match:
                break
        
        if not port_match:
            log_output("Failed to parse Jupyter output for port and token", "error")
            log_output(f"Jupyter output: {full_jupyter_output}", "error")
            raise Exception(f"Failed to parse Jupyter Notebook port and token. Output: {full_jupyter_output}")
        
        remote_port = port_match.group(1)
        token = port_match.group(2)
        
        log_output(f"Jupyter running on port {remote_port}", "success")
        log_output(f"Access token: {token[:8]}...", "info")
        
        # Step 5: Create an SSH tunnel using the gateway host
        log_output("Creating SSH tunnel...", "info")
        gateway_host = ssh_client.get_transport().getpeername()[0]
        username = ssh_client.get_transport().get_username()
        
        tunnel_cmd = f"ssh -L {local_port}:{best_server}:{remote_port} -N {username}@{gateway_host}"
        
        log_output(f"Tunnel: localhost:{local_port} -> {best_server}:{remote_port}", "info")
        
        # Start the tunnel in a separate process
        tunnel_process = subprocess.Popen(
            tunnel_cmd, 
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Store tunnel process for cleanup
        global active_tunnel_process
        active_tunnel_process = tunnel_process
        
        # Give some time for the tunnel to establish
        time.sleep(3)
        
        # Step 6: Create the local URL
        notebook_url = f"http://localhost:{local_port}/?token={token}"
        log_output("SSH tunnel established successfully", "success")
        log_output(f"Jupyter Notebook URL: {notebook_url}", "success")
        
        # Open in browser
        webbrowser.open(notebook_url)
        log_output("Jupyter Notebook opened in browser", "success")
        
        return {
            "success": True,
            "url": notebook_url,
            "message": f"🟢 Jupyter Notebook started successfully! Access it at {notebook_url}",
            "port": remote_port,
            "token": token,
            "tunnel_process": tunnel_process
        }
        
    except Exception as e:
        error_msg = f"An error occurred while starting Jupyter Notebook: {str(e)}"
        log_output(error_msg, "error")
        return {
            "success": False,
            "error": str(e),
            "message": f"❌ {error_msg}"
        }

def send_command_to_active_shell(command):
    """Send a command to the active shell session."""
    global active_shell
    if active_shell is None:
        add_to_output_buffer("No active shell session", "error")
        return False
    
    try:
        add_to_output_buffer(f"$ {command}", "command")
        active_shell.send(command + '\n')
        time.sleep(1)  # Give time for command to execute
        
        # Collect output
        output = ""
        max_wait = 5  # Maximum wait time in seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if active_shell.recv_ready():
                chunk = active_shell.recv(4096).decode('utf-8')
                output += chunk
            else:
                time.sleep(0.1)
                if not active_shell.recv_ready():
                    break
        
        if output.strip():
            # Split output into lines and add each to buffer
            for line in output.strip().split('\n'):
                if line.strip():
                    add_to_output_buffer(line, "output")
        
        return True
        
    except Exception as e:
        add_to_output_buffer(f"Error sending command: {str(e)}", "error")
        return False

def kill_processes_on_port_with_timeout(port, timeout=3):
    """Kill processes on a port with timeout to avoid hanging."""
    import signal
    
    killed_processes = []
    try:
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Port cleanup timed out after {timeout} seconds")
        
        # Set alarm for timeout (Unix/Linux only)
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'connections']):
                try:
                    connections = proc.info['connections']
                    if connections:
                        for conn in connections:
                            if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                                # Try to terminate gracefully first
                                proc.terminate()
                                try:
                                    proc.wait(timeout=1)  # Wait 1 second for graceful termination
                                except psutil.TimeoutExpired:
                                    proc.kill()  # Force kill if it doesn't terminate
                                killed_processes.append(f"PID {proc.info['pid']} ({proc.info['name']})")
                                break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except TimeoutError:
            add_to_output_buffer(f"Port {port} cleanup timed out - continuing anyway", "warning")
        finally:
            # Cancel the alarm
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
                
    except Exception as e:
        add_to_output_buffer(f"Error during port cleanup: {e}", "warning")
    
    return killed_processes

def disconnect_session():
    """Disconnect the current Jupyter session and clean up resources with enhanced browser tab detection."""
    global active_shell, active_tunnel_process
    
    try:
        print("Starting session disconnect...")
        add_to_output_buffer("Disconnecting session...", "info")
        
        # Kill any active tunnel processes with timeout
        if 'active_tunnel_process' in globals() and active_tunnel_process:
            print("Terminating tunnel process...")
            add_to_output_buffer("Terminating SSH tunnel...", "warning")
            try:
                active_tunnel_process.terminate()
                # Wait with timeout
                try:
                    active_tunnel_process.wait(timeout=3)
                    add_to_output_buffer("SSH tunnel terminated gracefully", "success")
                except subprocess.TimeoutExpired:
                    add_to_output_buffer("SSH tunnel force-killed (timeout)", "warning")
                    active_tunnel_process.kill()
                    try:
                        active_tunnel_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        add_to_output_buffer("SSH tunnel process may still be running", "warning")
            except Exception as e:
                add_to_output_buffer(f"Error terminating tunnel: {e}", "warning")
            finally:
                active_tunnel_process = None
        
        # Close the active shell with timeout
        if active_shell:
            try:
                print("Closing active shell...")
                add_to_output_buffer("Closing shell session...", "warning")
                # Send Ctrl+C to interrupt any running processes
                active_shell.send('\x03')  # Ctrl+C
                time.sleep(0.5)  # Reduced wait time
                active_shell.close()
                add_to_output_buffer("Shell session closed", "success")
            except Exception as e:
                print(f"Error closing shell: {e}")
                add_to_output_buffer(f"Error closing shell: {e}", "warning")
            finally:
                active_shell = None
        
        # Enhanced port cleanup with better browser tab detection
        print("Cleaning up ports with timeout...")
        add_to_output_buffer("Cleaning up ports (with timeout)...", "info")
        
        cleanup_successful = 0
        cleanup_failed = 0
        browser_tabs_detected = 0
        
        for port in range(8888, 8893):  # Reduced range for faster cleanup
            try:
                # Check what's using the port before attempting cleanup
                port_usage = analyze_port_usage(port)
                
                if port_usage["is_free"]:
                    add_to_output_buffer(f"Port {port}: already free", "info")
                    continue
                
                # Attempt cleanup
                killed = kill_processes_on_port_with_timeout(port, timeout=2)
                
                if killed:
                    print(f"Cleaned up port {port}: {killed}")
                    add_to_output_buffer(f"Port {port}: {', '.join(killed)}", "success")
                    cleanup_successful += 1
                    
                    # Verify port is now free
                    time.sleep(0.5)
                    if not is_port_free(port):
                        add_to_output_buffer(f"Port {port}: still in use after cleanup", "warning")
                        cleanup_failed += 1
                else:
                    # Check if it's a browser tab
                    if port_usage["browser_connection"]:
                        add_to_output_buffer(f"Port {port}: browser tab still open (close manually)", "warning")
                        browser_tabs_detected += 1
                    else:
                        add_to_output_buffer(f"Port {port}: in use by {port_usage['process_name']}", "warning")
                    cleanup_failed += 1
                    
            except Exception as e:
                print(f"Error cleaning port {port}: {e}")
                add_to_output_buffer(f"Port {port}: cleanup error - {e}", "warning")
                cleanup_failed += 1
        
        # Enhanced summary messages
        if cleanup_failed > 0:
            summary_msg = f"Port cleanup: {cleanup_successful} freed, {cleanup_failed} still in use"
            add_to_output_buffer(summary_msg, "warning")
            
            if browser_tabs_detected > 0:
                browser_msg = f"⚠️  {browser_tabs_detected} browser tab(s) detected. Please close Jupyter notebook tabs manually."
                add_to_output_buffer(browser_msg, "warning")
                add_to_output_buffer("💡 Tip: Look for tabs with 'localhost:888X' in your browser", "info")
            
            if cleanup_failed - browser_tabs_detected > 0:
                other_processes = cleanup_failed - browser_tabs_detected
                add_to_output_buffer(f"⚠️  {other_processes} port(s) blocked by other processes", "warning")
        else:
            add_to_output_buffer(f"✅ Port cleanup: {cleanup_successful} ports freed", "success")
        
        # Final status message
        if browser_tabs_detected > 0:
            add_to_output_buffer("🔄 Session disconnected (manual browser cleanup needed)", "warning")
        else:
            add_to_output_buffer("✅ Session disconnected successfully", "success")
            
        print("Session disconnected and resources cleaned up")
        
    except Exception as e:
        print(f"Error during disconnect: {e}")
        add_to_output_buffer(f"Error during disconnect: {e}", "error")

def is_port_free(port, host='localhost'):
    """Check if a port is free, with enhanced checking for lingering connections."""
    import socket
    import time
    
    # First check: basic socket connection
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            s.listen(1)
        except OSError:
            # Port is in use
            return False
    
    # Second check: look for processes using this port
    try:
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status in ['LISTEN', 'ESTABLISHED']:
                return False
    except (psutil.AccessDenied, AttributeError):
        # If we can't check processes, rely on socket test
        pass
    
    # Third check: try to actually connect to see if something is listening
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        result = s.connect_ex((host, port))
        if result == 0:
            # Something is listening on this port
            return False
    
    return True

def find_free_port(start_port=8888, max_attempts=20):
    """Find a free port starting from start_port with detailed feedback."""
    port = start_port
    attempted_ports = []
    browser_ports = []
    
    for attempt in range(max_attempts):
        attempted_ports.append(port)
        
        if is_port_free(port):
            if len(attempted_ports) > 1:
                add_to_output_buffer(f"🎯 Found free port {port} after checking {len(attempted_ports)} ports", "success")
            return port
        else:
            # Analyze what's using this port
            port_usage = analyze_port_usage(port)
            
            if port_usage["browser_connection"]:
                browser_ports.append(port)
                add_to_output_buffer(f"🌐 Port {port} in use (browser tab)", "info")
            else:
                add_to_output_buffer(f"⚙️  Port {port} in use ({port_usage['process_name']})", "info")
        
        port += 1
    
    # Provide helpful error message
    error_msg = f"Could not find a free port after checking {max_attempts} ports ({start_port}-{port-1})"
    if browser_ports:
        error_msg += f"\n🌐 Browser tabs detected on ports: {', '.join(map(str, browser_ports))}"
        error_msg += "\n💡 Close browser tabs to free up ports"
    
    raise Exception(error_msg)

def smart_port_cleanup_and_find(preferred_port=8888):
    """Smart port cleanup with enhanced feedback and browser tab detection."""
    
    # First, try the preferred port
    if is_port_free(preferred_port):
        add_to_output_buffer(f"✅ Port {preferred_port} is available", "success")
        return preferred_port
    
    # Analyze what's using the preferred port
    port_usage = analyze_port_usage(preferred_port)
    
    if port_usage["browser_connection"]:
        add_to_output_buffer(f"🌐 Port {preferred_port} in use by browser tab", "warning")
        add_to_output_buffer("💡 You may close the browser tab to reuse this port", "info")
    else:
        add_to_output_buffer(f"⚠️  Port {preferred_port} in use by {port_usage['process_name']}", "warning")
    
    # Try to clean up the preferred port with timeout
    add_to_output_buffer(f"🔧 Attempting to clean up port {preferred_port}...", "info")
    try:
        killed = kill_processes_on_port_with_timeout(preferred_port, timeout=3)
        if killed:
            add_to_output_buffer(f"✅ Cleaned up port {preferred_port}: {', '.join(killed)}", "success")
            time.sleep(1)  # Brief wait for cleanup
            
            # Check if it's now free
            if is_port_free(preferred_port):
                add_to_output_buffer(f"🎉 Port {preferred_port} is now available", "success")
                return preferred_port
            else:
                add_to_output_buffer(f"⚠️  Port {preferred_port} still in use after cleanup", "warning")
        else:
            add_to_output_buffer(f"❌ Could not clean up port {preferred_port}", "warning")
    except Exception as e:
        add_to_output_buffer(f"❌ Cleanup attempt failed: {e}", "warning")
    
    # If still not free, find an alternative
    add_to_output_buffer(f"🔍 Finding alternative port (starting from {preferred_port + 1})...", "info")
    
    try:
        alternative_port = find_free_port(preferred_port + 1)
        add_to_output_buffer(f"✅ Using alternative port: {alternative_port}", "success")
        add_to_output_buffer(f"🔗 Jupyter will be available at: localhost:{alternative_port}", "info")
        return alternative_port
    except Exception as e:
        add_to_output_buffer(f"❌ Could not find alternative port: {e}", "error")
        add_to_output_buffer("💡 Try closing browser tabs or restarting the application", "info")
        raise

def kill_processes_on_port(port):
    """Kill any processes using the specified port."""
    killed_processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                connections = proc.info['connections']
                if connections:
                    for conn in connections:
                        if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                            proc.kill()
                            killed_processes.append(f"PID {proc.info['pid']} ({proc.info['name']})")
                            break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        print(f"Error killing processes on port {port}: {e}")
    
    return killed_processes

def analyze_port_usage(port):
    """Analyze what is using a specific port and detect browser connections."""
    result = {
        "is_free": True,
        "browser_connection": False,
        "process_name": "unknown",
        "connection_type": "none",
        "pid": None
    }
    
    # First check if port is free with basic socket test
    if is_port_free(port):
        return result
    
    result["is_free"] = False
    
    try:
        # Check for processes using this port
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                connections = proc.info.get('connections', [])
                if not connections:
                    continue
                    
                for conn in connections:
                    if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                        result["pid"] = proc.info['pid']
                        result["process_name"] = proc.info['name']
                        result["connection_type"] = conn.status
                        
                        # Detect browser connections based on process name and connection status
                        browser_processes = ['chrome', 'firefox', 'edge', 'safari', 'msedge', 'chromium']
                        if any(browser in result["process_name"].lower() for browser in browser_processes):
                            result["browser_connection"] = True
                        elif conn.status == 'ESTABLISHED' and result["process_name"] in ['jupyter-notebook', 'jupyter', 'python']:
                            # This might be a browser connection to Jupyter
                            result["browser_connection"] = True
                        
                        return result
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        # If we get here, port is in use but we couldn't identify the process
        # Check network connections without process info
        for conn in psutil.net_connections():
            if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                result["connection_type"] = conn.status
                if conn.status == 'ESTABLISHED':
                    result["browser_connection"] = True  # Likely browser connection
                break
                
    except Exception as e:
        result["process_name"] = f"error: {e}"
    
    return result