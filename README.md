# Gundi Portal

This repository holds code for Gundi's Portal. It provides a web interface as well as a restful API for integration functions to use.

# Prerequisites

* Terraform (used for rendering templated Kubernetes manifests)
* Docker Desktop with Kubernetes enabled
* kubectl 

# Optional but recommended
* Kong API Gateway

## Building a cdip-portal image

`docker build -t cdip-portal:latest -f docker/Dockerfile .`

