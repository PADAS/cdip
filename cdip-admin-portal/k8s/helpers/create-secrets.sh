#!/bin/bash

# This script will create a self-signed certifcate and an accompanying private key.
# The two files will be loaded into a Kubernetes secret where deployments can find them.

KUBERNETES_NAMESPACE=cdip-v1

# Create the namespace if it doesn't exist.
kubectl get ns ${KUBERNETES_NAMESPACE} || kubectl create ns ${KUBERNETES_NAMESPACE}

# Load these files into a secret where deployments find them.
kubectl -n ${KUBERNETES_NAMESPACE} create secret generic ssl-certificate-data \
    --from-file=pamdas-org-private-key-pem=privatekey.pem \
    --from-file=pamdas-org-ssl-cert-bundle=fullchain.pem

