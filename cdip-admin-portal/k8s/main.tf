locals {

}

resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templates"
  destination_dir = "${path.root}/rendered"

  vars = {
    KUBERNETES_NAMESPACE   = var.namespace
    CDIP_PORTAL_IMAGE = var.cdip_portal_image
    CDIP_API_IMAGE = var.cdip_api_image
    SITE_FQDN = var.site-fqdn
//    ALLOWED_HOSTS = var.allowed-hosts
  }
}

variable "namespace" {
  type    = string
  default = "cdip"
}

variable "cdip_portal_image" {
  type    = string
  default = "gcr.io/cdip-78ca/cdip-portal:latest"
}

variable "cdip_api_image" {
  type = string
  default = "gcr.io/cdip-78ca/cdip-api:latest"
}

variable "site-fqdn" {
  type = string
}

//variable "allowed-hosts" {
//  type = list(string)
//  default = []
//}
