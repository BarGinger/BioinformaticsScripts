import paramiko
import time
import re
import webbrowser
import subprocess

ssh_client = None

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

import threading
import queue

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