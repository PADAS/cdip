locals {

}

resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templates"
  destination_dir = "${path.root}/rendered"

  vars = {
    KUBERNETES_NAMESPACE   = var.namespace
    FUNCTIONS_NAMESPACE = var.functions-namespace
    CDIP_PORTAL_IMAGE = var.cdip_portal_image
    CDIP_API_IMAGE = var.cdip_api_image
    AIRFLOW_IMAGE = var.airflow_image
    SITE_FQDN = var.site-fqdn
    AIRFLOW_FQDN = var.airflow-fqdn

//    ALLOWED_HOSTS = var.allowed-hosts
  }
}

variable "namespace" {
  type    = string
  default = "cdip"
}

variable "functions-namespace" {
  type    = string
}

variable "cdip_portal_image" {
  type    = string
  default = "gcr.io/cdip-78ca/cdip-portal:latest"
}

variable "cdip_api_image" {
  type = string
  default = "gcr.io/cdip-78ca/cdip-api:latest"
}

variable "airflow_image" {
  type = string
  default = "gcr.io/cdip-78ca/cdip-airflow-1.10.12:latest"
}

variable "site-fqdn" {
  type = string
}

variable "airflow-fqdn" {
  type = string
}

//variable "allowed-hosts" {
//  type = list(string)
//  default = []
//}
