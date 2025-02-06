import subprocess
import re
import webbrowser
import time
import os
import socket
import sys
import threading
import queue
import argparse

# Configuration
remote_host = "wildtype1.bio.uu.nl"
gateway_host = "alive.bio.uu.nl"
username = "bar"
local_port = 8888

def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) != 0

# Find a free local port
while not is_port_free(local_port):
    local_port += 1

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line.decode('utf-8'))
    out.close()


def get_command_output(q, timeout=10):
    last_output_time = time.time()
    output = ""
    while True:
        try:
            line = q.get_nowait()
            output += line
            print(line.strip())
            last_output_time = time.time()
        except queue.Empty:
            if time.time() - last_output_time > timeout:
                break
    return output

def find_best_server(awi_output):
    lines = awi_output.splitlines()
    best_server = None
    max_gb_avail = 0.0

    for line in lines:
        match = re.search(r'(\d+\.\d+)\s+\d+\.\d+\s+\d+\s+(\w+)\s+\w+-\d+\s+(\d+\.\d+)', line)
        if match:
            gb_avail = float(match.group(3))
            server = match.group(2)
            if gb_avail > max_gb_avail:
                max_gb_avail = gb_avail
                best_server = server

    return best_server

def set_up(username="bar", gateway_host="alive.bio.uu.nl", env_name="bio", dest_folder="Projects"):
    # Step 1: SSH into the gateway and run the 'awi' command
    ssh_cmd = f'ssh -tt -o StrictHostKeyChecking=no {username}@{gateway_host}'
    process = subprocess.Popen(ssh_cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = ""

    q = queue.Queue()
    t = threading.Thread(target=enqueue_output, args=(process.stdout, q))
    t.daemon = True
    t.start()

    # Wait for the SSH connection to be established
    output = get_command_output(q, timeout=6)

    # Run the 'awi' command in the same SSH session
    process.stdin.write(b"aiw\n")
    process.stdin.flush()
    awi_output = get_command_output(q, timeout=6)

    # Step 2: Find the best server based on available GB
    best_server = find_best_server(awi_output)
    if not best_server:
        raise Exception("No suitable server found.")

    print(f"Best server found: {best_server}")
    # Step 3: SSH into the best server
    process.stdin.write(b"ssh " + best_server.encode('utf-8') + b"\n")
    process.stdin.flush()
    output = get_command_output(q, timeout=6)
    
    if "Last login" in output:
        print(f"Successfully connected to {best_server}")
        # Step 4: Activate the conda environment
        process.stdin.write(f"conda activate {env_name}\n".encode('utf-8'))
        process.stdin.flush()
        # Check the current environment
        process.stdin.write(f"echo $CONDA_DEFAULT_ENV\n".encode('utf-8'))
        process.stdin.flush()


        output = get_command_output(q, timeout=6)
    else:
        print(f"Failed to connect to {best_server}")
        raise Exception("SSH connection failed")
    

    if f"\n{env_name}\r\n" not in output:
            print(f"Failed to activate conda environment: {env_name}")
            raise Exception("Conda environment activation failed")
    
    # Step 5: cd into the desired directory
    process.stdin.write(f"cd {dest_folder}\n".encode('utf-8'))
    process.stdin.flush()
    # Check if cd was successful
    process.stdin.write(b"pwd\n")
    process.stdin.flush()
    
    output = get_command_output(q, timeout=6)

    if dest_folder not in output:
        print(f"Failed to change directory to: {dest_folder}")
        raise Exception("Change directory failed")

    return process, q, best_server



def run_jupyter(process, q, username, gateway_host, best_server):    
    # Step 6: Return the jupyter notebook command
    process.stdin.write(f"jupyter notebook --ip 0.0.0.0 --no-browser\n".encode('utf-8'))
    process.stdin.flush()
    output = get_command_output(q, timeout=15)

    # Extract port and token from the output
    port_match = re.search(r'http://.*:(\d+)/\w*\?token=(\w+)', output)
    if port_match:
        remote_port = port_match.group(1)
        token = port_match.group(2)

        # Step 7: Create an SSH tunnel to the Jupyter port
        tunnel_cmd = f'ssh {username}@{gateway_host} -L {local_port}:{best_server}:{remote_port}'
        tunnel_process = subprocess.Popen(tunnel_cmd, shell=True)

        # Give some time for the tunnel to establish
        time.sleep(5)

        # Step 8: Open the Jupyter Notebook in the local browser
        notebook_url = f"http://localhost:{local_port}/?token={token}"
        webbrowser.open(notebook_url)

        print(f"Jupyter Notebook should now be accessible at {notebook_url}")

        # Ensure the SSH tunnel is properly closed on script exit
        try:
            tunnel_process.wait()
        except KeyboardInterrupt:
            tunnel_process.terminate()
        else:
            raise Exception("Failed to parse Jupyter Notebook port and token.")
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Jupyter Notebook on a remote server.")
    parser.add_argument("--username", type=str, default="bar", help="Username for SSH")
    parser.add_argument("--gateway_host", type=str, default="alive.bio.uu.nl", help="Gateway host for SSH")
    parser.add_argument("--env_name", type=str, default="bio", help="Conda environment name")
    parser.add_argument("--dest_folder", type=str, default="Projects", help="Destination folder")

    args = parser.parse_args()

    process, q, best_server = set_up(username=args.username, gateway_host=args.gateway_host, env_name=args.env_name, dest_folder=args.dest_folder)
    run_jupyter(process, q, username, gateway_host, best_server)
