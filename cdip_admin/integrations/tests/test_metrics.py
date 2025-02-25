import pytest
from integrations.models import IntegrationStatus, Integration
from ..metrics import calculate_data_frequency


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "observation_traces_spikes,expected_metrics",
    [
        (  # Mostly every 8 hours with one extra spike in the middle
                [(24, 'hours'), (16, 'hours'), (8, 'hours'), (1, 'hours'), (0, 'hours'), ],
                [60, 480, 480]
        ),
        (  # Most commonly every 30 minutes with some outliers
                [(300, 'minutes'), (180, 'minutes'), (150, 'minutes'), (120, 'minutes'), (112, 'minutes'),
                 (90, 'minutes'), (60, 'minutes'), ],
                [10, 120, 30]
        ),
        (  # Exactly every 10 minutes
                [(50, 'minutes'), (40, 'minutes'), (30, 'minutes'), (20, 'minutes'), (10, 'minutes'),],
                [10, 10, 10]
        ),
        (  # Every about 10 minutes
                [(50, 'minutes'), (40, 'minutes'), (29, 'minutes'), (20, 'minutes'), (7, 'minutes'),],
                [10, 10, 10]  # Intervals are rounded to nearest 10 minutes
        ),
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
