import pytest

from deployments.tasks import get_function_request


def _configuration(**deployment_settings):
    return {
        "env_vars": {"GCP_PROJECT_ID": "cdip-test"},
        "deployment_settings": {
            "region": "us-central1",
            "bucket_name": "dispatchers-code-test",
            "source_code_path": "er-dispatcher-src.zip",
            "service_account": "dispatchers@cdip-test.iam.gserviceaccount.com",
            **deployment_settings,
        },
    }


@pytest.mark.parametrize(
    "deployment_settings, expected_memory",
    [
        ({}, "256M"),  # platform default when the deployment does not say
        ({"memory": "512M"}, "512M"),
    ],
)
def test_get_function_request_sets_memory_from_deployment_settings(
    deployment_settings, expected_memory
):
    request = get_function_request(
        configuration=_configuration(**deployment_settings),
        function_name="Test-Dispatcher",
        topic_path="projects/cdip-test/topics/test-topic",
    )

    service_config = request.function.service_config
    assert service_config.available_memory == expected_memory
    # Unchanged neighbours keep their defaults.
    assert service_config.available_cpu == "1"
    assert service_config.max_instance_request_concurrency == 4
