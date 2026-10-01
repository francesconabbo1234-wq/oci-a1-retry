"""Tries to create the Always Free Ampere A1 VM on Oracle Cloud (run by GitHub Actions, see LOOP_MINUTES).

Everything account-specific comes from environment variables (repository secrets):
  OCI_USER, OCI_TENANCY, OCI_FINGERPRINT, OCI_REGION, OCI_KEY (API private key, PEM text)
  SSH_PUBLIC_KEY                          public key allowed to log in as "ubuntu"
  PAR_ARCHIVE, PAR_SETUP, PAR_BACKUP      pre-authenticated download links of the server files (Object Storage)
Optional: INSTANCE_NAME (default "minecraft"), SUBNET_NAME (default "public-subnet"), OCPUS (1), MEMORY_GB (6),
LOOP_MINUTES (keep retrying for this long, default 0 = one attempt), INTERVAL (seconds between attempts, default 60).

Exit codes: 0 = created, already there, or no capacity (normal, retried later); 1 = unexpected error.
Writes "result=created|exists|capacity|throttled" and "instance_id=..." to $GITHUB_OUTPUT when set.
"""
import base64
import os
import random
import sys
import time

import oci

NAME = os.environ.get("INSTANCE_NAME", "minecraft")
SUBNET_NAME = os.environ.get("SUBNET_NAME", "public-subnet")
OCPUS = float(os.environ.get("OCPUS", "1"))
MEMORY_GB = float(os.environ.get("MEMORY_GB", "6"))
LOOP_MINUTES = float(os.environ.get("LOOP_MINUTES", "0"))  # 0 = a single attempt
INTERVAL = int(os.environ.get("INTERVAL", "60"))


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    for k, v in kv.items():
        print(f"{k}={v}")
        if path:
            with open(path, "a") as f:
                f.write(f"{k}={v}\n")


config = {
    "user": os.environ["OCI_USER"].strip(),
    "tenancy": os.environ["OCI_TENANCY"].strip(),
    "fingerprint": os.environ["OCI_FINGERPRINT"].strip(),
    "region": os.environ["OCI_REGION"].strip(),
    "key_content": os.environ["OCI_KEY"],
}
oci.config.validate_config(config)
tenancy = config["tenancy"]
compute = oci.core.ComputeClient(config)
network = oci.core.VirtualNetworkClient(config)
identity = oci.identity.IdentityClient(config)

# never two VMs
for inst in compute.list_instances(compartment_id=tenancy, display_name=NAME).data:
    if inst.lifecycle_state not in ("TERMINATED", "TERMINATING"):
        print(f"instance already exists: {inst.lifecycle_state}")
        output(result="exists", instance_id=inst.id)
        sys.exit(0)

ad = identity.list_availability_domains(compartment_id=tenancy).data[0].name
subnet = network.list_subnets(compartment_id=tenancy, display_name=SUBNET_NAME).data[0].id
images = compute.list_images(compartment_id=tenancy, operating_system="Canonical Ubuntu",
                             operating_system_version="24.04 Minimal aarch64", shape="VM.Standard.A1.Flex",
                             sort_by="TIMECREATED", sort_order="DESC").data
image = images[0]

# first boot: download the server files and install everything (Java 25, service, firewall, backups)
user_data = f"""#!/bin/bash
exec > /var/log/minecraft-bootstrap.log 2>&1
set -x
cd /home/ubuntu
fetch() {{ for i in $(seq 1 20); do python3 -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" "$1" "$2" && return 0; sleep 30; done; return 1; }}
fetch '{os.environ["PAR_SETUP"].strip()}' setup-server.sh
fetch '{os.environ["PAR_BACKUP"].strip()}' mc-backup.sh
fetch '{os.environ["PAR_ARCHIVE"].strip()}' aeronautics-server.tar.gz
chown ubuntu:ubuntu setup-server.sh mc-backup.sh aeronautics-server.tar.gz
sudo -u ubuntu -H bash /home/ubuntu/setup-server.sh
echo BOOTSTRAP-DONE
"""

details = oci.core.models.LaunchInstanceDetails(
    compartment_id=tenancy,
    availability_domain=ad,
    display_name=NAME,
    shape="VM.Standard.A1.Flex",
    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=OCPUS, memory_in_gbs=MEMORY_GB),
    source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=image.id, boot_volume_size_in_gbs=50),
    create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet, assign_public_ip=True),
    metadata={
        "ssh_authorized_keys": os.environ["SSH_PUBLIC_KEY"].strip(),
        "user_data": base64.b64encode(user_data.encode()).decode(),
    },
)
# GitHub's cron fires only a few times a day on this repo, so each run keeps trying for LOOP_MINUTES
# (one attempt every INTERVAL seconds, longer pauses after a 429); the workflow then starts the next run itself
deadline = time.time() + LOOP_MINUTES * 60
attempts = 0
while True:
    attempts += 1
    try:
        inst = compute.launch_instance(details, retry_strategy=oci.retry.NO_RETRY_STRATEGY).data
        break
    except oci.exceptions.ServiceError as e:
        text = f"{e.status} {e.code} {e.message}"
        if e.status == 429:
            result, pause = "throttled", random.randint(300, 900)
        elif "capacity" in text.lower():
            result, pause = "capacity", INTERVAL
        else:
            print(f"[{time.strftime('%H:%M:%S')}] attempt {attempts}: unexpected error: {text}")
            sys.exit(1)
        print(f"[{time.strftime('%H:%M:%S')}] attempt {attempts}: {result}: {text}", flush=True)
    if time.time() + pause > deadline:
        print(f"{attempts} attempts, no VM yet")
        output(result=result, attempts=attempts)
        sys.exit(0)
    time.sleep(pause)

print(f"CREATED {inst.id} ({OCPUS:g} OCPU / {MEMORY_GB:g} GB, image {image.display_name}) after {attempts} attempts")
output(result="created", instance_id=inst.id, attempts=attempts)
