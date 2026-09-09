data "oci_identity_availability_domains" "available" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "ubuntu_arm64" {
  count                    = var.ubuntu_image_ocid == "" ? 1 : 0
  compartment_id           = var.tenancy_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = var.instance_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

locals {
  selected_ad = var.availability_domain != "" ? var.availability_domain : data.oci_identity_availability_domains.available.availability_domains[0].name
  image_ocid  = var.ubuntu_image_ocid != "" ? var.ubuntu_image_ocid : data.oci_core_images.ubuntu_arm64[0].images[0].id
}

resource "oci_core_instance" "pilot" {
  availability_domain = local.selected_ad
  compartment_id      = var.compartment_ocid
  display_name        = var.display_name
  shape               = var.instance_shape

  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gb
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.pilot.id
    assign_public_ip = var.assign_public_ip
    display_name     = "zhituo-pilot-vnic"
    hostname_label   = "zhituo-pilot"
  }

  source_details {
    source_type             = "image"
    source_id               = local.image_ocid
    boot_volume_size_in_gbs = var.boot_volume_size_gb
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
      display_name = var.display_name
    }))
  }

  is_pv_encryption_in_transit_enabled = true

  lifecycle {
    precondition {
      condition     = var.always_free_acknowledged
      error_message = "Refusing apply until authenticated tenancy usage confirms enough Always Free capacity."
    }
    precondition {
      condition     = var.region == var.home_region
      error_message = "Always Free compute and block volume must be created in the tenancy home region."
    }
    precondition {
      condition     = var.instance_shape == "VM.Standard.A1.Flex" && var.instance_ocpus <= 2 && var.instance_memory_gb <= 12
      error_message = "Compute request exceeds this module's current Always Free A1 boundary."
    }
  }
}
