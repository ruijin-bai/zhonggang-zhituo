resource "oci_core_vcn" "pilot" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.42.0.0/16"]
  display_name   = "zhituo-pilot-vcn"
  dns_label      = "zhituopilot"
}

resource "oci_core_internet_gateway" "pilot" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.pilot.id
  display_name   = "zhituo-pilot-internet-gateway"
  enabled        = true
}

resource "oci_core_route_table" "pilot" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.pilot.id
  display_name   = "zhituo-pilot-route-table"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.pilot.id
  }
}

resource "oci_core_security_list" "pilot" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.pilot.id
  display_name   = "zhituo-pilot-restricted-security-list"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  ingress_security_rules {
    protocol = "6"
    source   = var.ssh_ingress_cidr
    tcp_options {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_subnet" "pilot" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.pilot.id
  cidr_block                 = "10.42.10.0/24"
  display_name               = "zhituo-pilot-public-subnet"
  dns_label                  = "pilot"
  route_table_id             = oci_core_route_table.pilot.id
  security_list_ids          = [oci_core_security_list.pilot.id]
  prohibit_public_ip_on_vnic = !var.assign_public_ip
}
