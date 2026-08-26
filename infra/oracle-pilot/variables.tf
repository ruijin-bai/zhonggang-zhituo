variable "tenancy_ocid" {
  description = "OCI tenancy OCID; provide outside Git."
  type        = string
  sensitive   = true
}

variable "compartment_ocid" {
  description = "Compartment for the Pilot resources."
  type        = string
  sensitive   = true
}

variable "region" {
  description = "OCI region. It must be the tenancy home region for Always Free resources."
  type        = string
}

variable "home_region" {
  description = "Home-region key confirmed from the authenticated tenancy."
  type        = string
}

variable "availability_domain" {
  description = "Optional AD name. Empty selects the first AD returned by OCI."
  type        = string
  default     = ""
}

variable "ssh_public_key" {
  description = "OpenSSH public key for the Ubuntu account."
  type        = string
  sensitive   = true
}

variable "ssh_ingress_cidr" {
  description = "Single trusted operator IP in CIDR form, normally x.x.x.x/32."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_ingress_cidr, 0)) && var.ssh_ingress_cidr != "0.0.0.0/0"
    error_message = "ssh_ingress_cidr must be a valid restricted CIDR and cannot be 0.0.0.0/0."
  }
}

variable "always_free_acknowledged" {
  description = "Set true only after the Console/API shows enough remaining Always Free quota."
  type        = bool
  default     = false
}

variable "instance_shape" {
  description = "Hard-limited to the current Always Free Ampere A1 shape."
  type        = string
  default     = "VM.Standard.A1.Flex"

  validation {
    condition     = var.instance_shape == "VM.Standard.A1.Flex"
    error_message = "Only VM.Standard.A1.Flex is allowed by this Free Tier module."
  }
}

variable "instance_ocpus" {
  description = "Current Always Free total is 2 OCPUs."
  type        = number
  default     = 2

  validation {
    condition     = var.instance_ocpus > 0 && var.instance_ocpus <= 2
    error_message = "instance_ocpus must be within the current 2-OCPU Always Free total."
  }
}

variable "instance_memory_gb" {
  description = "Current Always Free total is 12 GB memory."
  type        = number
  default     = 12

  validation {
    condition     = var.instance_memory_gb >= 1 && var.instance_memory_gb <= 12
    error_message = "instance_memory_gb must be between 1 and the current 12-GB Always Free total."
  }
}

variable "boot_volume_size_gb" {
  description = "Boot volume, counted within the tenancy's 200-GB Always Free block total."
  type        = number
  default     = 100

  validation {
    condition     = var.boot_volume_size_gb >= 50 && var.boot_volume_size_gb <= 200
    error_message = "boot_volume_size_gb must be between 50 and 200 GB. Verify remaining tenancy quota before apply."
  }
}

variable "assign_public_ip" {
  description = "Public IP for restricted SSH. Application ports remain closed."
  type        = bool
  default     = true
}

variable "ubuntu_image_ocid" {
  description = "Optional confirmed Always Free-eligible Ubuntu 24.04 ARM64 image OCID. Empty selects the newest matching image."
  type        = string
  default     = ""
}

variable "display_name" {
  type    = string
  default = "zhituo-oracle-pilot"
}
