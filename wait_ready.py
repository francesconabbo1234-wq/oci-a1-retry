"""After the VM is created: waits for RUNNING, reads the public IP, then waits (up to 60 minutes) until the Minecraft
server answers a status ping. Writes "ip=..." and "ping=..." to $GITHUB_OUTPUT."""
import os
import subprocess
import sys
import time

import oci

config = {k: os.environ[v] for k, v in
          {"user": "OCI_USER", "tenancy": "OCI_TENANCY", "fingerprint": "OCI_FINGERPRINT", "region": "OCI_REGION", "key_content": "OCI_KEY"}.items()}
compute = oci.core.ComputeClient(config)
network = oci.core.VirtualNetworkClient(config)
instance_id = sys.argv[1]


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    for k, v in kv.items():
        print(f"{k}={v}")
        if path:
            with open(path, "a") as f:
                f.write(f"{k}={v}\n")


oci.wait_until(compute, compute.get_instance(instance_id), "lifecycle_state", "RUNNING", max_wait_seconds=1800)
ip = None
while not ip:
    for att in compute.list_vnic_attachments(compartment_id=config["tenancy"], instance_id=instance_id).data:
        if att.lifecycle_state == "ATTACHED":
            ip = network.get_vnic(att.vnic_id).data.public_ip
    if not ip:
        time.sleep(15)
output(ip=ip)

deadline = time.time() + 3600
ping = "no answer after 60 minutes (the first boot installs Java and unpacks 2.7 GB: check again later)"
while time.time() < deadline:
    r = subprocess.run([sys.executable, "mc_ping.py", ip], capture_output=True, text=True)
    if r.returncode == 0:
        ping = r.stdout.strip()
        break
    time.sleep(30)
output(ping=ping.replace("\n", " "))
