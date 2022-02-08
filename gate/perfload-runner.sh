#!/bin/bash -x

WORK_DIR=$1

# Do some performance related information gathering for placement.
EXPLANATION="
This output combines output from placeload with timing information
gathered via curl. The placeload output is the current maximum
microversion of placement followed by an encoded representation of
what it has done. Lowercase 'r', 'i', 'a', and 't' indicate successful
creation of a resource provider and setting inventory, aggregates, and
traits on that resource provider.

If there are upper case versions of any of those letters, a failure
happened for a single request. The letter will be followed by the
HTTP status code and the resource provider uuid. These can be used
to find the relevant entry in logs/placement-api.log.

Note that placeload does not exit with an error code when this
happens. It merely reports and moves on. Under correct circumstances
the right output is a long string of 4000 characters containing
'r', 'i', 'a', 't' in random order (because async).

After that are three aggregate uuids, timing information for the
placeload run, and then timing information for two identical curl
requests for allocation candidates.

If no timed requests are present it means that the expected number
of resource providers were not created. At this time, only resource
providers are counted, not whether they have the correct inventory,
aggregates, or traits.

"

# This aggregate uuid is a static value in placeload.
AGGREGATE="14a5c8a3-5a99-4e8f-88be-00d85fcb1c17"
TRAIT="HW_CPU_X86_AVX2"
PLACEMENT_QUERY="resources=VCPU:1,DISK_GB:10,MEMORY_MB:256&member_of=${AGGREGATE}&required=${TRAIT}"
PLACEMENT_URL="http://127.0.0.1:8000"


LOG=placement-perf.txt
LOG_DEST=${WORK_DIR}/logs
COUNT=1000

# Apache Benchmark Concurrency
AB_CONCURRENT=10
# Apache Benchmark Total Requests
AB_COUNT=500

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
    rc=$?
    # curl -f will fail silently on server errors and return code 22
    # When used with -s, --silent, -S makes curl show an error message if it fails
    # If we failed to write an allocation, skip measurements and log a message
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
    for iter in {1..99}; do
      echo "##### Writing allocation ${iter}" | tee -a $LOG
      write_allocation
      time_candidates
    done
}

function check_placement {
    local rp_count
    local code
    code=0

    python3 -m venv .placeload
    . .placeload/bin/activate

    # install placeload
    pip install 'placeload==0.3.0'

    set +x
    # load with placeload
    (
        echo "$EXPLANATION"
        # preheat the aggregates to avoid https://bugs.launchpad.net/nova/+bug/1804453
        placeload $PLACEMENT_URL 10
        echo "##### TIMING placeload creating $COUNT resource providers with inventory, aggregates and traits."
        time placeload $PLACEMENT_URL $COUNT
    ) 2>&1 | tee -a $LOG
    rp_count=$(curl -H 'x-auth-token: admin' ${PLACEMENT_URL}/resource_providers |json_pp|grep -c '"name"')
    # If we failed to create the required number of rps, skip measurements and
    # log a message.
    if [[ $rp_count -ge $COUNT ]]; then
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
