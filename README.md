# oci-a1-retry

Tries every 5 minutes to create an Oracle Cloud **Always Free** Ampere A1 VM (the region often answers
"Out of host capacity"). When it succeeds, the VM installs a Minecraft server on its first boot (cloud-init), the
workflow waits until the server answers, opens an issue with the address and disables itself.

- `launch.py`: one launch attempt; never creates a second VM.
- `wait_ready.py`: waits for RUNNING, the public IP and a Minecraft status ping.
- `mc_ping.py`: Minecraft Server List Ping.

No account data is in this repository: everything comes from the repository secrets
(`OCI_USER`, `OCI_TENANCY`, `OCI_FINGERPRINT`, `OCI_REGION`, `OCI_KEY`, `SSH_PUBLIC_KEY`, `PAR_ARCHIVE`,
`PAR_SETUP`, `PAR_BACKUP`).
