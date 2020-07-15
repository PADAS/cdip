# CDIP Local Development

First of all, some assumptions:

* You've cloned the [cdip repository](https://github.com/PADAS/cdip)  
* You would like to run the full stack in Kubernetes, locally. *And you have enabled kubernetes in Docker Desktop.*

## Some prerequisites

* [Terraform](https://learn.hashicorp.com/terraform/getting-started/install.html) (used for rendering templated Kubernetes manifests)

* [Docker Desktop](https://www.docker.com/products/docker-desktop) with Kubernetes enabled
* [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/) 


## Building a cdip-portal image

Step one is to build an image for clip-portal. From within the cdip-admin-portal folder, run this command below. This might take a few minutes the first time you build it.

```bash
docker build -t cdip-portal:latest -f docker/Dockerfile .
```


## Deploy to Kubernetes

Once you've build an image for cdip-portal, you're ready to deploy it to a kubernetes cluster. This article assumes you have a Kubernetes cluster (probably Docker Desktop) and can interact with it usin `kubectl`.



### Prepare to render templates

```
# navigate to the k8s directory (cdip/cdip-admin-portal/k8s)
cd k8s

# Create your own copy of input variables
cp local-dev.auto.tfvars.example local-dev.auto.tfvars
```

Edit `local-dev.auto.tfvars` and follow the comments in that file. This will allow you to specify a local folder for your own source code as well as database and upload files.

### Render Templates

This task uses Terraform template plugin to render Kubernetes manifests.

```bash
terraform init
terraform apply
```

### Apply to Kubernetes

Now that you've rendered your manifests, you can apply them to your Kubernetes cluster.

```bash
kubectl -n cdip apply -Rf rendered/
```

### Verify the Deployment

You've created several resources in your cluster's **cdip** namespace. You can see what it created using this:

```
kubectl -n cdip get all
```

