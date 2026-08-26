output "instance_id" {
  value = oci_core_instance.pilot.id
}

output "region" {
  value = var.region
}

output "availability_domain" {
  value = local.selected_ad
}

output "shape" {
  value = "${var.instance_shape}: ${var.instance_ocpus} OCPU / ${var.instance_memory_gb} GB"
}

output "architecture" {
  value = "linux/arm64"
}

output "public_ip" {
  value = oci_core_instance.pilot.public_ip
}

output "private_ip" {
  value = oci_core_instance.pilot.private_ip
}

output "ssh_command" {
  value = var.assign_public_ip ? "ssh ubuntu@${oci_core_instance.pilot.public_ip}" : "Use OCI Bastion to reach ubuntu@${oci_core_instance.pilot.private_ip}"
}
