#!/bin/bash -x
WORK_DIR=$1

PLACEMENT_URL="http://127.0.0.1:8000"
LOG=placement-perf.txt
LOG_DEST=${WORK_DIR}/logs
# The gabbit used to create one nested provider tree. It takes
# inputs from LOADER to create a unique tree.
GABBIT=gate/gabbits/nested-perfload.yaml
LOADER=gate/perfload-nested-loader.sh

# The query to be used to get a list of allocation candidates. If
# $GABBIT is changed, this may need to change.
TRAIT="COMPUTE_VOLUME_MULTI_ATTACH"
TRAIT1="CUSTOM_FOO"
PLACEMENT_QUERY="resources=DISK_GB:10&required=${TRAIT}&resources_COMPUTE=VCPU:1,MEMORY_MB:256&required_COMPUTE=${TRAIT1}&resources_FPGA=FPGA:1&group_policy=none&same_subtree=_COMPUTE,_FPGA"

# Number of nested trees to create.
ITERATIONS=1000

# Number of times to write allocations and then time again.
ALLOCATIONS_TO_WRITE=10

# Apache Benchmark Concurrency
AB_CONCURRENT=10
# Apache Benchmark Total Requests
AB_COUNT=500

# The number of providers in each nested tree. This will need to
# change whenever the resource provider topology created in $GABBIT
# is changed.
PROVIDER_TOPOLOGY_COUNT=7
# Expected total number of providers, used to check that creation
# was a success.
TOTAL_PROVIDER_COUNT=$((ITERATIONS * PROVIDER_TOPOLOGY_COUNT))

trap "sudo cp -p $LOG $LOG_DEST" EXIT

function time_candidates {
    (
        echo "##### TIMING GET /allocation_candidates?${PLACEMENT_QUERY} twice"
        time curl -s -H 'x-auth-token: admin' -H 'openstack-api-version: placement latest' "${PLACEMENT_URL}/allocation_candidates?${PLACEMENT_QUERY}" > /dev/null
        time curl -s -H 'x-auth-token: admin' -H 'openstack-api-version: placement latest' "${PLACEMENT_URL}/allocation_candidates?${PLACEMENT_QUERY}" > /dev/null
    ) 2>&1 | tee -a $LOG
}

function ab_bench {
    (
        echo "#### Running apache benchmark"
        ab -c $AB_CONCURRENT -n $AB_COUNT -H 'x-auth-token: admin' -H 'openstack-api-version: placement latest' "${PLACEMENT_URL}/allocation_candidates?${PLACEMENT_QUERY}"
    ) 2>&1 | tee -a $LOG
}

function write_allocation {
    # Take the first allocation request and send it back as a well-formed allocation
    curl -s -H 'x-auth-token: admin' -H 'openstack-api-version: placement latest' "${PLACEMENT_URL}/allocation_candidates?${PLACEMENT_QUERY}&limit=5" \
        | jq --arg proj $(uuidgen) --arg user $(uuidgen) '.allocation_requests[0] + {consumer_generation: null, project_id: $proj, user_id: $user, consumer_type: "TEST"}' \
        | curl -f -s -S -H 'x-auth-token: admin' -H 'content-type: application/json' -H 'openstack-api-version: placement latest' \
            -X PUT -d @- "${PLACEMENT_URL}/allocations/$(uuidgen)"
    # curl -f will fail silently on server errors and return code 22
    # When used with -s, --silent, -S makes curl show an error message if it fails
    # If we failed to write an allocation, skip measurements and log a message
    rc=$?
    if [[ $rc -eq 22 ]]; then
        echo "Failed to write allocation due to a server error. See logs/placement-api.log for additional detail."
        exit 1
    elif [[ $rc -ne 0 ]]; then
        echo "Failed to write allocation, curl returned code: $rc. See job-output.txt for additional detail."
        exit 1
    fi
}

function load_candidates {
    time_candidates
    for iter in $(seq 1 $ALLOCATIONS_TO_WRITE); do
      echo "##### Writing allocation ${iter}" | tee -a $LOG
      write_allocation
      time_candidates
    done
}

function check_placement {
    local rp_count
    local code
    code=0

    python3 -m venv .perfload
    . .perfload/bin/activate

    # install gabbi
    pip install gabbi

    # Create $TOTAL_PROVIDER_COUNT nested resource provider trees,
    # each tree having $PROVIDER_TOPOLOGY_COUNT resource providers.
    # LOADER is called $ITERATIONS times in parallel using 50% of
    # the number of processors on the host.
    echo "##### Creating $TOTAL_PROVIDER_COUNT providers" | tee -a $LOG
    seq 1 $ITERATIONS | parallel -P 50% $LOADER $PLACEMENT_URL $GABBIT

    set +x
    rp_count=$(curl -H 'x-auth-token: admin' ${PLACEMENT_URL}/resource_providers |json_pp|grep -c '"name"')
    # If we failed to create the required number of rps, skip measurements and
    # log a message.
    if [[ $rp_count -ge $TOTAL_PROVIDER_COUNT ]]; then
      load_candidates
      ab_bench
    else
        (
            echo "Unable to create expected number of resource providers. Expected: ${COUNT}, Got: $rp_count"
            echo "See job-output.txt.gz and logs/placement-api.log for additional detail."
        ) | tee -a $LOG
        code=1
    fi
    set -x
    deactivate
    exit $code
}

check_placement
