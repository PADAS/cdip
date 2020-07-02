locals {

}

resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templates"
  destination_dir = "${path.root}/rendered"

  vars = {
    KUBERNETES_NAMESPACE   = var.namespace
    CDIP_PORTAL_SOURCE_PATH = var.cdip_portal_source_path
    LOCAL_DATABASE_STORAGE = var.local_database_storage
    LOCAL_MEDIA_STORAGE    = var.local_media_storage
    FQDN                   = var.fqdn
  }
}

variable "namespace" {
  type    = string
  default = "cdip"
}

variable "cdip_portal_source_path" {
  type    = string
  default = ""
}

variable "local_database_storage" {
  type = string
}

variable "local_media_storage" {
  type = string
}

variable "fqdn" {
  type = string
  default = "localhost:31443"
}
