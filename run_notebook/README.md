# Run Jupyter Notebook on a Remote Server

This script allows you to run a Jupyter Notebook on a remote server and access it through an SSH tunnel.

## Prerequisites

1. Python 3.12
2. SSH access to the remote server
3. Conda installed on the remote server
4. Enable StrictHostKeyChecking

    In order for the scripts to work, you need to enable passwordless SSH login. Follow these steps to set it up:

    1) Generate SSH Key Pair:
        ```bash
        ssh-keygen -t rsa -b 4096
        ```

        This command generates a new SSH key pair. Follow the prompts to save the key pair to the default location (~/.ssh/id_rsa) and optionally set a passphrase.

    2) Copy Public Key to Remote Server:

        ```bash
        ssh-copy-id -i ~/.ssh/id_rsa.pub <your_username>@alive.bio.uu.nl
        ```

    3) Verify SSH Key Authentication
        ```bash
        ssh <your_username>@alive.bio.uu.nl
        ```


## Installation

1. Clone this repository or download the script.
2. Ensure you have Python 3.12 installed on your local machine.

## Usage

To run the script, use the following command:

```bash
python run_notebook.py --username <your_username> --gateway_host <gateway_host> --env_name <conda_env_name> --dest_folder <destination_folder>
```

### Arguments
--username: (Required) Your SSH username. Default is bar.
--gateway_host: (Required) The gateway host for SSH. Default is alive.bio.uu.nl.
--env_name: (Required) The name of the Conda environment to activate. Default is bio.
--dest_folder: (Required) The destination folder to change to. Default is Projects.

### Example

```bash
python run_notebook.py --username bar --gateway_host alive.bio.uu.nl --env_name bio --dest_folder Projects
```

## How It Works
The script SSHs into the gateway host and runs the awi command to find the best server based on available GB.
It then SSHs into the best server and activates the specified Conda environment.
The script changes to the specified destination folder.
It starts a Jupyter Notebook on the remote server.
An SSH tunnel is created to forward the Jupyter Notebook port to your local machine.
The Jupyter Notebook is opened in your local web browser.

### Troubleshooting
Ensure you have SSH access to the remote server.
Make sure Conda is installed and the specified environment exists on the remote server.
Verify that the destination folder exists on the remote server.

## License
This project is licensed under the MIT License.