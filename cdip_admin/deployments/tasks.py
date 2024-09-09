import google.auth
from celery import shared_task
from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.types import pubsub_gapic_types
from google.cloud import functions_v2, run_v2
from google.cloud import eventarc_v1
from google.cloud.eventarc_v1 import CreateTriggerRequest
from google.cloud.eventarc_v1.types import Trigger, Destination, CloudRun
from google.api_core.exceptions import AlreadyExists, NotFound
from django.apps import apps
from django.conf import settings
from . import utils


if settings.GCP_ENVIRONMENT_ENABLED:
    credentials, project_id = google.auth.default()
    pubsub_client = pubsub_v1.PublisherClient()  # This raises  credentials error when running in th CI pipeline
    subscriptions_client = pubsub_v1.SubscriberClient()
    functions_client = functions_v2.FunctionServiceClient()
    cloudrun_client = run_v2.ServicesClient(credentials=credentials)
    eventarc_client = eventarc_v1.EventarcClient(credentials=credentials)
    DISPATCHER_DEFAULT_SETTINGS_ER = utils.get_dispatcher_defaults_from_gcp_secrets(
        secret_id=settings.DISPATCHER_DEFAULTS_SECRET
    )
    DISPATCHER_DEFAULT_SETTINGS_SMART = utils.get_dispatcher_defaults_from_gcp_secrets(
        secret_id=settings.DISPATCHER_DEFAULTS_SECRET_SMART
    )
    DISPATCHER_DEFAULT_SETTINGS_WPSWATCH = utils.get_dispatcher_defaults_from_gcp_secrets(
        secret_id=settings.DISPATCHER_DEFAULTS_SECRET_WPSWATCH
    )
else:
    pubsub_client = utils.PubSubDummyClient()
    subscriptions_client = utils.SubscriberDummyClient()
    functions_client = utils.FunctionsDummyClient()
    cloudrun_client = utils.CloudRunDummyClient()
    eventarc_client = utils.EventarcDummyClient()
    DISPATCHER_DEFAULT_SETTINGS_ER = {}
    DISPATCHER_DEFAULT_SETTINGS_SMART = {}


def get_function_subscription_request(function, topic_path, configuration):
    function_name = function.name
    deployment_settings = configuration.get("deployment_settings", {})
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    function_id = function_name.split("/")[5]
    subscription_name = f"{function_id[:250]}-sub".replace("--", "-")
    push_endpoint = function.service_config.uri
    service_account = deployment_settings.get("service_account")
    subscription = pubsub_gapic_types.Subscription(
        name=f"projects/{project_id}/subscriptions/{subscription_name}",
        topic=topic_path,
        push_config=pubsub_gapic_types.PushConfig(
            push_endpoint=push_endpoint,
            oidc_token=pubsub_gapic_types.PushConfig.OidcToken(
                service_account_email=service_account,
                audience=push_endpoint
            )
        ),
        expiration_policy=pubsub_gapic_types.ExpirationPolicy(),
        ack_deadline_seconds=600,
        enable_message_ordering=True,
        retry_policy=pubsub_gapic_types.RetryPolicy(
            minimum_backoff="10s",
            maximum_backoff="600s"
        )
    )
    return subscription


def get_service_subscription_request(service_response, topic_path, configuration):
    service_name = service_response.name
    deployment_settings = configuration.get("deployment_settings", {})
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    service_id = service_name.split("/")[5]
    subscription_name = f"{service_id[:250]}-sub".replace("--", "-")
    push_endpoint = service_response.uri
    service_account = deployment_settings.get("service_account")
    subscription = pubsub_gapic_types.Subscription(
        name=f"projects/{project_id}/subscriptions/{subscription_name}",
        topic=topic_path,
        push_config=pubsub_gapic_types.PushConfig(
            push_endpoint=push_endpoint,
            oidc_token=pubsub_gapic_types.PushConfig.OidcToken(
                service_account_email=service_account,
                audience=push_endpoint
            )
        ),
        expiration_policy=pubsub_gapic_types.ExpirationPolicy(),
        ack_deadline_seconds=600,
        enable_message_ordering=True,
        retry_policy=pubsub_gapic_types.RetryPolicy(
            minimum_backoff="10s",
            maximum_backoff="600s"
        )
    )
    return subscription


@shared_task
def deploy_serverless_dispatcher(deployment_id, force_recreate=False, deployment_settings=None):
    DispatcherDeployment = apps.get_model("deployments", "DispatcherDeployment")
    deployment = DispatcherDeployment.objects.get(id=deployment_id)
    deployment.status = DispatcherDeployment.Status.IN_PROGRESS
    deployment.status_details = ""  # Clean previous errors
    deployment.save()

    # Get settings from the database
    if deployment.integration:  # v2 models
        gundi_version = "v2"
        integration = deployment.integration
    elif deployment.legacy_integration:  # legacy models
        gundi_version = "v1"
        integration = deployment.legacy_integration
    else:
        error_msg = f"Either integration or legacy_integration field must be set"
        print(error_msg)
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = error_msg[:500]
        deployment.save()
        return
    function_name = deployment.name or utils.get_default_dispatcher_name(integration=integration, gundi_version=gundi_version)
    if not deployment.configuration:  # Use default settings
        deployment.configuration = DISPATCHER_DEFAULT_SETTINGS_ER
    configuration = deployment.configuration
    if deployment_settings:
        configuration["deployment_settings"].update(deployment_settings)
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    topic = integration.additional.get("topic", utils.get_default_topic_name(integration=integration, gundi_version=gundi_version))
    topic_path = f'projects/{project_id}/topics/{topic}'
    deployment.topic_name = topic  # Save the topic for retries or deletions
    deployment.save()

    try:
        create_topic(topic_path=topic_path)

        # Create the dispatcher
        if integration.is_er_site:  # Deploy a Cloud function
            function_request = get_function_request(
                configuration=configuration,
                function_name=function_name,
                topic_path=topic_path
            )

            if force_recreate:
                try:
                    delete_function(function_name=function_name, configuration=configuration)
                except NotFound as e:
                    print(f"Function {function_name} not found. Skipping deletion.")
                except Exception as e:
                    print(f"Error deleting function {function_name}: {e}")
                    deployment.status = DispatcherDeployment.Status.ERROR
                    deployment.status_details = f"Error deleting function {function_name}: {e}"
                    deployment.save()
                    return
            function_response = create_or_update_function(
                function_request=function_request,
            )
            # Create a subscription to the topic
            subscription = get_function_subscription_request(function_response, topic_path, configuration)
            create_subscription(request=subscription)
        elif integration.is_smart_site or integration.is_wpswatch_site:  # Deploy a Cloud Run Service

            if force_recreate:
                try:
                    delete_cloudrun_service(service_name=function_name, configuration=configuration)
                except NotFound as e:
                    print(f"Cloudrun Service {function_name} not found. Skipping deletion.")
                except Exception as e:
                    print(f"Error deleting Cloudrun service {function_name}: {e}")
                    deployment.status = DispatcherDeployment.Status.ERROR
                    deployment.status_details = f"Error deleting Cloudrun service {function_name}: {e}"
                    deployment.save()
                    return

            service_response = create_or_update_cloud_run_service(
                configuration=configuration,
                service_name=function_name,
                topic_path=topic_path,
                force_recreate=force_recreate
            )
            # Create a subscription to the topic
            subscription = get_service_subscription_request(service_response, topic_path, configuration)
            create_subscription(request=subscription)
        else:
            error_msg = f"Integration type '{integration.type.value}' is not supported."
            print(error_msg)
            deployment.status = DispatcherDeployment.Status.ERROR
            deployment.status_details = error_msg[:500]
            deployment.save()
            return
        print(f"Deploy complete.")
        deployment.status = DispatcherDeployment.Status.COMPLETE
        deployment.save()
    except Exception as e:  # ToDo: Catch more specific errors like validation errors?
        error_msg = f"Error deploying function: {e}"
        print(error_msg)
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = error_msg[:500]
        deployment.save()
        return


@shared_task
def delete_serverless_dispatcher(deployment_id, topic):
    print(f"Deleting dispatcher deployment {deployment_id}...")
    DispatcherDeployment = apps.get_model("deployments", "DispatcherDeployment")
    deployment = DispatcherDeployment.objects.get(id=deployment_id)
    is_er_site = deployment.integration.is_er_site if deployment.integration else False
    deployment.integration = None  # Unlink from integrations as they might be being deleted
    deployment.legacy_integration = None
    deployment.status = DispatcherDeployment.Status.DELETING
    deployment.status_details = ""  # Clean previous errors
    deployment.save()

    try:
        if is_er_site:
            response = delete_function(function_name=deployment.name, configuration=deployment.configuration)
        else:  # SMART or others will use Cloud Run
            response = delete_cloudrun_service(service_name=deployment.name, configuration=deployment.configuration)
    except NotFound as e:
        print(f"Function or Service {deployment.name} not found. Skipping deletion.")
    except Exception as e:
        error_msg = f"Error deleting function: {e}"
        print(error_msg)
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = error_msg[:500]
        deployment.save()
    else:
        print(response)
        print("Function or Service deletion complete.")

    try:
        delete_topic(topic_name=topic, configuration=deployment.configuration)
    except NotFound as e:
        print(f"Topic {topic} not found. Skipping deletion.")
    except Exception as e:
        print(f"Error deleting topic {topic}: {e}")
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = f"Error deleting topic {topic}: {e}"
        deployment.save()
        return
    else:
        print("Topic deletion complete.")

    try:
        subscription_name = f"{deployment.name[:250]}-sub".replace("--", "-")
        delete_subscription(
            subscription_name=subscription_name,
            configuration=deployment.configuration
        )
    except NotFound as e:
        print(f"Subscription {subscription_name} not found. Skipping deletion.")
    except Exception as e:
        print(f"Error deleting subscription {subscription_name}: {e}")
        deployment.status = DispatcherDeployment.Status.ERROR
        deployment.status_details = f"Error deleting subscription {subscription_name}: {e}"
        deployment.save()
        return
    else:
        print(f"Subscription deletion complete.")
    # No errors deleting resources in GCP
    deployment.delete()  # Remove it from the DB


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
        print(f"Creating function {function_request.function_id} ...")
        operation = functions_client.create_function(request=function_request)
        print(f"Waiting for the operation to finish..")
        print(operation)
        response = operation.result()
        print(response)
        print(f"Function {function_request.function_id} CREATED.")
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
        print(response)
        print(f"Function {function_request.function_id} UPDATED.")
        return response


def create_subscription(request):
    try:
        print(f"Creating subscription {request.name} ...")
        response = subscriptions_client.create_subscription(request=request)
        print(response)
        print(f"Subscription {request.name} CREATED.")
    except AlreadyExists:
        print(f"Subscription {request.name} already exists. Skipping creation.")
        return
    return response


def delete_subscription(subscription_name, configuration):
    print(f"Deleting subscription {subscription_name} ...")
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    full_subscription_name = f"projects/{project_id}/subscriptions/{subscription_name}"
    subscription_request = pubsub_gapic_types.DeleteSubscriptionRequest(
        subscription=full_subscription_name
    )
    response = subscriptions_client.delete_subscription(request=subscription_request)
    print(f"Subscription {subscription_name} DELETED.")
    return response



def delete_function(function_name, configuration):
    print(f"Deleting CLoud function {function_name} ...")
    deployment_settings = configuration.get("deployment_settings", {})
    region = deployment_settings.get("region", "us-central1")
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    full_function_name = f"projects/{project_id}/locations/{region}/functions/{function_name}"
    function_request = functions_v2.DeleteFunctionRequest(
        name=full_function_name
    )
    operation = functions_client.delete_function(
        request=function_request
    )
    response = operation.result()
    print(f"Function {function_name} DELETED.")
    return response


def delete_cloudrun_service(service_name, configuration):
    print(f"Deleting CloudRun service {service_name} ...")
    deployment_settings = configuration.get("deployment_settings", {})
    region = deployment_settings.get("region", "us-central1")
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    full_service_name = f"projects/{project_id}/locations/{region}/services/{service_name}"
    delete_request = run_v2.types.DeleteServiceRequest(
        name=full_service_name
    )
    operation = cloudrun_client.delete_service(
        request=delete_request
    )
    response = operation.result()
    print(f"Service {service_name} DELETED.")
    return response


def delete_topic(topic_name, configuration):
    print(f"Deleting Topic {topic_name}...")
    env_vars = configuration.get("env_vars", {})
    project_id = env_vars.get("GCP_PROJECT_ID")
    topic_path = f'projects/{project_id}/topics/{topic_name}'
    pubsub_client.delete_topic(topic=topic_path)
    print(f"Topic {topic_name} DELETED.")


def create_or_update_cloud_run_service(configuration, service_name, topic_path, force_recreate=False):
    print(f"Deploying Cloud Run service {service_name}...")
    deployment_settings = configuration.get("deployment_settings", {})
    region = deployment_settings.get("region", "us-central1")
    env_vars = configuration.get("env_vars", {})
    env_var_objects = [run_v2.types.EnvVar(name=key, value=value) for key, value in env_vars.items()]
    project_id = env_vars.get("GCP_PROJECT_ID")
    image_url = deployment_settings.get("docker_image_url")
    vpc_connector_name = deployment_settings.get("vpc_connector")
    vpc_connector_path = f"projects/{project_id}/locations/{region}/connectors/{vpc_connector_name}"
    min_instances = deployment_settings.get("min_instances", 0)
    max_instances = deployment_settings.get("max_instances", 2)
    parent = f"projects/{project_id}/locations/{region}"
    # Define the service resource
    service = run_v2.types.Service(
        template=run_v2.types.RevisionTemplate(
            containers=[run_v2.types.Container(
                image=image_url,
                env=env_var_objects
            )],
            vpc_access=run_v2.types.VpcAccess(
                connector=vpc_connector_path
            ),
            scaling=run_v2.types.RevisionScaling(
                min_instance_count=min_instances,
                max_instance_count=max_instances
            )
        ),
        ingress=run_v2.types.IngressTraffic.INGRESS_TRAFFIC_INTERNAL_ONLY
    )
    # Define the CreateServiceRequest
    request = run_v2.types.CreateServiceRequest(
        parent=parent,
        service=service,
        service_id=service_name
    )
    # Deploy the service
    try:
        operation = cloudrun_client.create_service(request=request)
        response = operation.result()
        print(f"Service {service_name} CREATED.")
    except AlreadyExists:
        print(f"Service {service_name} already exists.")
        print(f"Updating service {service_name}..")
        # Retrieve the current service configuration
        service_resource_name = f"projects/{project_id}/locations/{region}/services/{service_name}"
        current_service = cloudrun_client.get_service(name=service_resource_name)
        # Update the configuration
        current_service.template.containers[0].image = image_url
        current_service.template.containers[0].env = env_var_objects
        current_service.template.vpc_access.connector = vpc_connector_path
        current_service.template.scaling.min_instance_count = min_instances
        current_service.template.scaling.max_instance_count = max_instances
        # Update the service
        operation = cloudrun_client.update_service(service=current_service)
        response = operation.result()
        print(f"Service {service_name} UPDATED.")
    return response
