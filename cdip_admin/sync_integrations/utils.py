import json
import logging
from datetime import datetime, timezone

from smartconnect import SmartClient

from integrations.models import OutboundIntegrationConfiguration
import unicodedata

logger = logging.getLogger(__name__)


def maintain_smart_integration(*args, integration_id: str, force=False):
    '''
    This function is called when a SMART integration is saved. It inspects the Integration Configuration
    and will use a Smart Client to download whichever data models and configurable data models are associated
    with it.
    '''
    assert not args, "This function does not accept positional arguments"

    config = OutboundIntegrationConfiguration.objects.get(id=integration_id)

    if not force and not config.state.get('download_data_models', False):
        return

    version = config.additional.get("version", "7.0")
    use_language_code = config.additional.get("use_language_code", "en")

    smart_client = SmartClient(
        api=config.endpoint,
        username=config.login,
        password=config.password,
        use_language_code=use_language_code,
        version=version,
    )
    ca_uuids = config.additional.get("ca_uuids")
    configurable_models_lists = {}
    for ca_uuid in ca_uuids:
        try:
            smart_client.get_data_model(ca_uuid=ca_uuid, force=True)
            smart_client.get_conservation_area(ca_uuid=ca_uuid, force=True)
            cm_values = smart_client.list_configurable_datamodels(ca_uuid=ca_uuid)

            print(json.dumps(cm_values, indent=2))

            configurable_models_lists[ca_uuid] = cm_values

            for cm in cm_values:
                if cm.get('use_with_earth_ranger', True):
                    logger.info('Downloading configurable model %s (%s)', cm['name'], cm['uuid'])
                    smart_client.get_configurable_data_model(cm_uuid=cm['uuid'], force=True)
                else:
                    logger.info('Skipping configurable model %s (%s)', cm['name'], cm['uuid'])
        except Exception as e:
            logger.exception(e, extra=dict(ca_uuid=ca_uuid))

    config.additional['configurable_models_lists'] = configurable_models_lists
    config.state['download_data_models'] = False
    config.state['data_models_downloaded_at'] = datetime.now(tz=timezone.utc).isoformat()
    config.save()

def unicode_to_ascii(input_string, replacement=''):
    """
    Convert a Unicode string to an ASCII string, using a specified replacement string
    for those that cannot be converted directly.

    Args:
    input_string (str): The Unicode string to convert.
    replacement (str): The string to use for replacing non-ASCII characters.

    Returns:
    str: The ASCII version of the input string.
    """
    # Normalize the Unicode string to decompose characters into base characters and modifiers
    normalized_string = unicodedata.normalize('NFKD', input_string)

    # Encode to ASCII bytes, using the 'ignore' strategy to skip non-ASCII characters,
    # then decode back to string, this loses the characters which can't be directly converted
    ascii_string = normalized_string.encode('ASCII', 'ignore').decode('ASCII')

    # For any character that is not ASCII in the original normalized string, replace it
    result = []
    for char in normalized_string:
        if char in ascii_string:
            result.append(char)
        else:
            result.append(replacement)

    return ''.join(result)

