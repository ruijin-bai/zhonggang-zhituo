#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s <compartment-ocid> <region> <availability-domain> [oci-profile]\n' "$0" >&2
  exit 2
}

[[ $# -ge 3 && $# -le 4 ]] || usage
compartment_ocid="$1"
target_region="$2"
availability_domain="$3"
profile="${4:-DEFAULT}"

command -v oci >/dev/null 2>&1 || { printf 'FAIL: OCI CLI is required\n' >&2; exit 1; }

oci_args=(--profile "$profile" --region "$target_region")
home_region="$(oci iam region-subscription list --profile "$profile" --all \
  --query 'data[?"is-home-region"]."region-name" | [0]' --raw-output)"

[[ "$home_region" == "$target_region" ]] || {
  printf 'FAIL: target region %s is not tenancy home region %s\n' "$target_region" "$home_region" >&2
  exit 1
}

printf 'PASS: OCI authentication and home region=%s\n' "$home_region"
printf '==> A1 shape availability in requested AD\n'
oci compute shape list "${oci_args[@]}" --compartment-id "$compartment_ocid" \
  --availability-domain "$availability_domain" --all \
  --query 'data[?shape==`VM.Standard.A1.Flex`].{shape:shape,ocpus:ocpus,memory:"memory-in-gbs"}' \
  --output table

printf '==> Current compute limits returned by the tenancy\n'
oci limits value list "${oci_args[@]}" --service-name compute --all \
  --query 'data[?contains(name, `a1`) || contains(name, `A1`)].{name:name,value:value,scope:"scope-type"}' \
  --output table || true

printf '==> Existing boot volumes in the requested AD\n'
oci bv boot-volume list "${oci_args[@]}" --compartment-id "$compartment_ocid" \
  --availability-domain "$availability_domain" --all \
  --query 'data[].{name:"display-name",size_gb:"size-in-gbs",state:"lifecycle-state"}' \
  --output table

cat <<EOF
MANUAL-GATE: The OCI API output above does not prove billing eligibility by itself.
Confirm the Console shows Always Free-eligible for the exact Ubuntu ARM64 image, A1 shape and
remaining boot-volume allocation. Only then set always_free_acknowledged=true.
EOF
