# Connect to Alive Server

This script allows you to connect to the Alive server and perform various tasks.

## Prerequisites

1. SSH access to the Alive server

2. Enable StrictHostKeyChecking

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
2. Ensure you have SSH access to the Alive server.

## Usage

To run the script, use the following command:

```bash
./connect.sh
```

## Command-Line Arguments
-h: The gateway host for SSH. Default is alive.bio.uu.nl.
-u: Your SSH username. Default is bar.


# Example
```bash
./connect.sh -u john -h alive.bio.uu.nl
```


## How It Works
The script uses SSH to log into the initial host with pseudo-terminal allocation.


## Troubleshooting
Ensure you have SSH access to the Alive server.
Verify that the HOST and USER variables are correctly set in the script.

## License
This project is licensed under the MIT License.