#!/bin/bash
set -a
HOST=$1
GABBIT=$2

# By default the placement server is set up with noauth2 authentication
# handling. If that is changed to keystone, a $TOKEN can be generated in
# the calling environment and used instead of the default 'admin'.
TOKEN=${TOKEN:-admin}

# These are the dynamic/unique values for individual resource providers
# that need to be set for each run a gabbi file. Values that are the same
# for all the resource providers (for example, traits and inventory) should
# be set in $GABBIT.
CN1_UUID=$(uuidgen)
N0_UUID=$(uuidgen)
N1_UUID=$(uuidgen)
FPGA0_0_UUID=$(uuidgen)
FPGA1_0_UUID=$(uuidgen)
FPGA1_1_UUID=$(uuidgen)
PGPU0_0_UUID=$(uuidgen)

# Run gabbi silently.
gabbi-run -q $HOST -- $GABBIT
