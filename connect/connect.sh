#!/bin/bash

# Default variables
HOST="alive.bio.uu.nl"
USER="bar"

# Parse command-line arguments
while getopts "h:u:" opt; do
  case ${opt} in
    h )
      HOST=$OPTARG
      ;;
    u )
      USER=$OPTARG
      ;;
    \? )
      echo "Usage: cmd [-h] [-u]"
      exit 1
      ;;
  esac
done

# Use SSH to log into the initial host with pseudo-terminal allocation
ssh -tt -o StrictHostKeyChecking=no "$USER@$HOST"