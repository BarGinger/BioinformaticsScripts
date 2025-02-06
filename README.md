# BioinformaticsScripts

Useful scripts for bioinformatics lab.


## Enable StrictHostKeyChecking

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


## Scripts

### 1. Run Jupyter Notebook Remotely

This script allows you to run a Jupyter Notebook on a remote server and access it through an SSH tunnel.

[Read more](run_notebook/README.md)

### 2. Connect to Alive Server

This script allows you to connect to the Alive server and perform various tasks.

[Read more](connect/README.md)

## License

This project is licensed under the MIT License.