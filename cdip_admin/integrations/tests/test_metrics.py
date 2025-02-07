import pytest
from integrations.models import IntegrationStatus, Integration
from ..metrics import calculate_data_frequency


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "observation_traces_spikes,expected_metrics",
    [
        ([(24, 'hours'), (16, 'hours'), (8, 'hours'), (1, 'hours'), (0, 'hours'),], [60, 480, 480]),  # Every 8 hours
        ([(300, 'minutes'), (180, 'minutes'), (150, 'minutes'), (120, 'minutes'), (112, 'minutes'), (90, 'minutes'), (60, 'minutes'), ], [8, 120, 30]),  # Every 30 minutes

    ],
    indirect=['observation_traces_spikes']
)
def test_calculate_data_frequency_metric_from_traces(
        provider_lotek_panthera,
        observation_traces_spikes,
        expected_metrics
):
    f_min, f_max, f_typical = calculate_data_frequency(data_provider_id=provider_lotek_panthera.id)
    exp_min, exp_max, exp_typical = expected_metrics
    assert f_min == exp_min
    assert f_max == exp_max
    assert f_typical == exp_typical
