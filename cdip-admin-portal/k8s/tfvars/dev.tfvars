namespace = "cdip-v1"
functions-namespace = "cdip-functions"
metrics-namespace = "metrics"
site-fqdn = "cdip-dev.pamdas.org"
airflow-fqdn = "airflow.pamdas.org"
api-fqdn = "cdip-api.pamdas.org"
realm-suffix = "-dev"
airflow-gcs-logs-folder = "gs://cdip-78ca-airflow-dev-logs"

airflow-image-name = "gcr.io/cdip-78ca/cdip-airflow-metrics-1.10.12"
airflow-image-tag = "latest"
cdip_portal_image = "gcr.io/cdip-78ca/cdip-portal:latest"
cdip_api_image = "gcr.io/cdip-78ca/cdip-api:latest"

//cdip_portal_image = "gcr.io/cdip-78ca/cdip-portal@sha256:7957d5de720132bcea5bf8ac60d4c7f139d2567a04573f7af9b318188772d335"
//cdip_api_image = "gcr.io/cdip-78ca/cdip-api@sha256:afd1cb2bf25e0d9ae0a698ec7f703dcf6ae8a53983f40f7b39d1443dcbc4bcbc"

redis-host-ipaddress = "10.170.75.131"
portal-db-host-ipaddress = "172.22.160.3"
portal-db-name = "dev_cdipdb"
gitsync-branch-name = "dispatchers-transformers"
keycloak-client-uuid = "90d34a81-c70c-408b-ad66-7fa1bfe58892"