# cdip (aka SMART Integrate)

This repository holds code for SMART Integrate's Web Portal. It provides a web interface as well as a restful API for integration functions to use.

# Prerequisites

* Terraform (used for rendering templated Kubernetes manifests)
* Docker Desktop with Kubernetes enabled
* kubectl 


## Building a cdip-portal image

`docker build -t cdip-portal:latest -f docker/Dockerfile .`

