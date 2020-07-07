# Prerequisites

* Terraform (used for rendering templated Kubernetes manifests)
* Docker Desktop with Kubernetes enabled
* kubectl 


## Building a cdip-portal image

`docker build -t cdip-portal:latest -f docker/Dockerfile .`


## Deploy to Kubernetes

`cd k8s`

`cp local-dev.auto.tfvars.example local-dev.auto.tfvars`

- edit `local-dev.auto.tfvars` and follow the comments in that file. This will allow you to specify a local folder for your database and upload files.

`terraform apply`

`kubectl -n cdip apply -Rf rendered/`
