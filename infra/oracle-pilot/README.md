# Oracle Always Free Pilot IaC

This Terraform module creates one restricted Ubuntu ARM64 VM, VCN, subnet, route table, Internet
Gateway and security list. It does not create a load balancer, managed database, NAT Gateway or any
other optional resource.

## Hard Free Tier boundary

Oracle's Always Free documentation updated 2026-06-12 currently states:

- `VM.Standard.A1.Flex` totals **2 OCPUs and 12 GB memory** per tenancy;
- compute and Always Free block storage must be in the tenancy **home region**;
- boot and block volumes share a **200 GB** total;
- capacity can be unavailable by availability domain; do not switch to a paid shape;
- idle Always Free instances can be reclaimed.

The module validates the exact A1 shape, a maximum 2 OCPUs / 12 GB, a maximum 200-GB boot volume,
home-region equality and the explicit `always_free_acknowledged` gate. Static limits cannot prove
the tenancy's remaining quota. Before setting the gate to true, use the authenticated OCI Console at
**Governance & Administration -> Limits, Quotas and Usage** and verify the instance image and shape
show **Always Free-eligible** and the requested boot volume fits the remaining Always Free allocation.

If OCI reports `Out of host capacity`, try another AD in the same home region or wait. Never change
`instance_shape` to a paid shape; the variable validation rejects that change.

## Use

1. Install Terraform/OpenTofu and configure OCI API authentication outside this repository.
2. Copy `terraform.tfvars.example` to an ignored `.tfvars` file and fill real tenancy values.
3. Keep `always_free_acknowledged=false` for the first plan.
4. Confirm authenticated tenancy usage and the Console's Always Free labels, then set it to `true`.
5. Apply and use the `public_ip` output with `scripts/oracle-pilot-bootstrap.sh`.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -var-file=pilot.auto.tfvars
terraform apply -var-file=pilot.auto.tfvars

bash scripts/oracle-pilot-bootstrap.sh \
  ubuntu@VM_IP ~/.ssh/id_ed25519 owner@example.com <merged-main-sha>
```

The bootstrap waits for cloud-init, registers the VM-generated key as a read-only GitHub deploy key,
clones the private repository, verifies the requested SHA equals governed `origin/main`, deploys
Zhituo from the `main` branch, enables reboot recovery
and runs health checks. It needs authenticated `gh`, SSH access and a merged main SHA.

Only TCP 22 from `ssh_ingress_cidr` is allowed. Application access remains loopback/SSH-forwarded or
uses an outbound Cloudflare Tunnel. Do not add public rules for API, PostgreSQL, Redis or MinIO.

## State and secrets

Do not commit OCI OCIDs, API keys, fingerprints, private SSH keys, `.tfvars`, Terraform state,
`deploy/pilot/.env`, MinIO certificates or backups. Use an encrypted remote state only if one is
already governed; otherwise protect local state as a credential-bearing artifact.
