from celery import shared_task
from google.cloud import pubsub_v1
from google.cloud import functions_v2
from google.api_core.exceptions import AlreadyExists
from django.apps import apps

pubsub_client = pubsub_v1.PublisherClient()
functions_client = functions_v2.FunctionServiceClient()


@shared_task
def deploy_serverless_dispatcher(deployment_id):
    DispatcherDeployment = apps.get_model("deployments", "DispatcherDeployment")
    deployment = DispatcherDeployment.objects.get(id=deployment_id)
    deployment.status = DispatcherDeployment.Status.IN_PROGRESS
    deployment.save()

    # Get settings from the database
    if deployment.integration:  # v2 models
        integration = deployment.integration
    elif deployment.legacy_integration:  # legacy models
        integration = deployment.legacy_integration
    else:
        error_msg = f"Either integration or legacy_integration field must be set"
        print(error_msg)
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = error_msg
        deployment.save()
        return
    function_name = deployment.name or f"dispatch-{integration.id}-dev"
    configuration = deployment.configuration
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    topic = integration.additional.get("topic", "")  # ToDo: Use a default name
    topic_path = f'projects/{project_id}/topics/{topic}'

    try:
        function_request = get_function_request(
            configuration=configuration,
            function_name=function_name,
            topic_path=topic_path
        )
        create_topic(topic_path=topic_path)
        response = create_or_update_function(function_request=function_request)

        print(f"Deploy complete.")
        print(response)
        deployment.status = DispatcherDeployment.Status.COMPLETE
        deployment.save()
    except Exception as e:  # ToDo: Catch more specific errors like validation errors?
        error_msg = f"Error deploying function: {e}"
        print(error_msg)
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = error_msg
        deployment.save()
        return


@shared_task
def delete_serverless_dispatcher(deployment_id):
    DispatcherDeployment = apps.get_model("deployments", "DispatcherDeployment")
    deployment = DispatcherDeployment.objects.get(id=deployment_id)
    deployment.status = DispatcherDeployment.Status.IN_PROGRESS
    deployment.save()

    # Get settings from the database
    if deployment.integration:  # v2 models
        integration = deployment.integration
    elif deployment.legacy_integration:  # legacy models
        integration = deployment.legacy_integration
    else:
        error_msg = f"Either integration or legacy_integration field must be set"
        print(error_msg)
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = error_msg
        deployment.save()
        return
    function_name = deployment.name or f"dispatch-{integration.id}-dev"
    topic = integration.additional.get("topic", "")

    try:
        function_request = delete_function(function_name=function_name)
        delete_topic(topic_name=topic)

        response = create_or_update_function(function_request=function_request)
        print(f"Delete complete.")
        print(response)
        deployment.status = DispatcherDeployment.Status.DELETED
        deployment.save()
    except Exception as e:
        error_msg = f"Error deleting function: {e}"
        print(error_msg)
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = error_msg
        deployment.save()
        return


def create_topic(topic_path):
    try:
        print(f"Creating Topic {topic_path}..")
        pubsub_client.create_topic(name=topic_path)
    except AlreadyExists as e:
        print(f"Topic {topic_path} already exists. Skipping creation.")
    print(f"Topic {topic_path} ready.")


def get_function_request(configuration, function_name, topic_path):
    deployment_settings = configuration.get("deployment_settings", {})
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")

    print(f"Deployment Settings:\n{deployment_settings}")
    print(f"Env vars:\n{env_vars}")
    region = deployment_settings.get("region", "us-central1")
    parent = f"projects/{project_id}/locations/{region}"
    function_id = function_name.lower()
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
    return request


def create_or_update_function(function_request):
    try:
        operation = functions_client.create_function(request=function_request)
        print(f"Waiting for the operation to finish..")
        print(operation)
        response = operation.result()
        return response
    except AlreadyExists:
        print(f"Function {function_request.function_id} already exists.")
        print(f"Updating function {function_request.function_id}..")
        request = functions_v2.UpdateFunctionRequest(
            function=function_request.function
        )
        # Make the request
        operation = functions_client.update_function(request=request)
        print(f"Waiting for the operation to finish..")
        print(operation)
        response = operation.result()
        return response


def delete_function(function_name):
    print(f"Deleting {function_name} function.")
    function_request = functions_v2.DeleteFunctionRequest(
        name=function_name
    )
    operation = functions_client.delete_function(
        request=function_request
    )
    response = operation.result()
    return response


def delete_topic(topic_name):
    print(f"Deleting Topic {topic_name}..")
    request = pubsub_v1.DeleteTopicRequest(
        topic=topic_name,
    )
    pubsub_client.delete_topic(request=request)
