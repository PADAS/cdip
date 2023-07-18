from celery import shared_task
from google.cloud import pubsub_v1
from google.cloud import functions_v2
from google.api_core.exceptions import AlreadyExists
from django.apps import apps


pubsub_client = pubsub_v1.PublisherClient()
functions_client = functions_v2.FunctionServiceClient()


@shared_task
def deploy_serverless_dispatcher(deployment_id, model_version="v1"):
    # ToDo: make it idempotent
    DispatcherDeployment = apps.get_model("deployments", "DispatcherDeployment")
    deployment = DispatcherDeployment.objects.get(id=deployment_id)
    deployment.status = DispatcherDeployment.Status.IN_PROGRESS
    deployment.save()
    # Get settings from the database
    if model_version == "v2":
        integration = deployment.integration
    else:  # Default to v1
        integration = deployment.legacy_integration
    print(f"Deploying dispatcher for integration {integration}..")
    configuration = deployment.configuration
    env_vars = configuration.get("env_vars", {})

    # Create the topic
    # project_id = publisher.project # os.getenv('GOOGLE_CLOUD_PROJECT') # FixMe
    project_id = env_vars.get("GCP_PROJECT_ID")
    topic = integration.additional.get("topic", "")  # ToDo: Use a default name
    topic_path = f'projects/{project_id}/topics/{topic}'
    try:
        print(f"Creating Topic {topic}..")
        pubsub_client.create_topic(name=topic_path)
    except AlreadyExists as e:
        print(f"Topic {topic} already exists. Skipping creation.")
    except Exception as e:
        print(e)
        print(f"Error creating topic {topic}: {e}")
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.save()
        return

    try:  # Deploy the function
        # Prepare the settings for the cloud function
        function_name = deployment.name or f"disptch-{integration.id}-dev"
        deployment_settings = configuration.get("deployment_settings", {})
        region = deployment_settings.get("region", "us-central1")
        parent = f"projects/{project_id}/locations/{region}"
        function_id = function_name.lower()
        # Point to the source code in Cloud Storage
        bucket_name = deployment_settings.get("bucket_name")
        source_code_path = deployment_settings.get("source_code_path")
        storage_source = functions_v2.types.StorageSource(
            bucket=bucket_name,
            object_=source_code_path
        )
        source = functions_v2.types.Source(
            storage_source=storage_source
        )
        build_config = functions_v2.types.BuildConfig(
            entry_point="main",
            runtime="python38",
            source=source
        )
        event_trigger = functions_v2.types.EventTrigger(
            event_type="google.cloud.pubsub.topic.v1.messagePublished",
            pubsub_topic=topic_path,
            retry_policy=functions_v2.types.EventTrigger.RetryPolicy.RETRY_POLICY_RETRY
        )
        service_config = functions_v2.types.ServiceConfig(
            vpc_connector=deployment_settings.get("vpc_connector"),
            service_account_email=deployment_settings.get("service_account"),
            environment_variables=env_vars,
            available_cpu=deployment_settings.get("cpu", "1"),
            min_instance_count=deployment_settings.get("min_instances", 0),
            max_instance_count=deployment_settings.get("max_instances", 2),
            max_instance_request_concurrency=deployment_settings.get("concurrency", 4),
            timeout_seconds=120
        )
        # Define the function
        function = functions_v2.types.Function(
            name=f"{parent}/functions/{function_id}",
            description="A serverless dispatcher",
            build_config=build_config,
            event_trigger=event_trigger,
            service_config=service_config
        )
        request = functions_v2.CreateFunctionRequest(
            parent=parent,
            function=function,
            function_id=function_id
        )
        # Make the request
        print(f"Creating function {function_name}..")
        operation = functions_client.create_function(request=request)
        response = operation.result()
    except AlreadyExists as e:
        print(f"Function {function_id} already exists. Skipping creation.")
    except Exception as e:
        print(f"Error deploying function:{e}")
        deployment.status = DispatcherDeployment.Status.ERROR
    else:
        # Handle the response
        print(f"Deploy complete:")
        print(response)
        deployment.status = DispatcherDeployment.Status.COMPLETE
    finally:
        deployment.save()
