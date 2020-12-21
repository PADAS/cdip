locals {

}

resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templates"
  destination_dir = "${path.root}/rendered"

  vars = {
    KUBERNETES_NAMESPACE   = var.namespace
    FUNCTIONS_NAMESPACE = var.functions-namespace
    METRICS-NAMESPACE = var.metrics-namespace
    CDIP_PORTAL_IMAGE = var.cdip_portal_image
    CDIP_API_IMAGE = var.cdip_api_image
    SITE_FQDN = var.site-fqdn
    API_FQDN = var.api-fqdn
    REALM_SUFFIX=var.realm-suffix
    AIRFLOW_IMAGE_NAME = var.airflow-image-name
    AIRFLOW_IMAGE_TAG = var.airflow-image-tag
    AIRFLOW_FQDN = var.airflow-fqdn
    AIRFLOW_DAGS_VOLUME_CLAIM = format("%s-dags-volume-claim", var.namespace)
    AIRFLOW_DAGS_VOLUME = format("%s-dags-volume", var.namespace)
    AIRFLOW_GCS_LOGS_FOLDER = var.airflow-gcs-logs-folder
  }
}

variable "namespace" {
  type    = string
  default = "cdip"
}

variable "functions-namespace" {
  type    = string
}

variable "metrics-namespace" {
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

variable "airflow-image-name" {
  type = string
  default = "gcr.io/cdip-78ca/cdip-airflow-1.10.12"
}

variable "airflow-image-tag" {
  type = string
  default = "latest"
}

variable "site-fqdn" {
  type = string
}

variable "airflow-fqdn" {
  type = string
}

variable "api-fqdn" {
  type = string
}

variable "realm-suffix" {
  type = string
}

variable "airflow-gcs-logs-folder" {
  type = string
}