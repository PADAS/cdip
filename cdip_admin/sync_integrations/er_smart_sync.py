import json
import logging
import pathlib
import uuid
import re
from datetime import timezone, datetime, timedelta
from typing import List, Optional, Dict
from urllib.parse import urlparse

import pydantic
from cdip_connector.core.cloudstorage import get_cloud_storage
from cdip_connector.core.publisher import get_publisher
from cdip_connector.core.routing import TopicEnum
from cdip_connector.core.schemas import ERPatrol, EREvent, ERSubject, ERObservation
from dasclient.dasclient import DasClient, DasClientException
from pydantic import parse_obj_as
from smartconnect import SmartClient, DataModel
from smartconnect.er_sync_utils import (
    build_earth_ranger_event_types,
    er_event_type_schemas_equal,
    get_subjects_from_patrol_data_model,
    er_subjects_equal,
    EREventType,
    get_earth_ranger_last_poll,
    set_earth_ranger_last_poll,
)
from packaging import version

from cdip_admin import settings
from integrations.models import (
    OutboundIntegrationConfiguration,
    InboundIntegrationConfiguration,
)

logger = logging.getLogger(__name__)

class ConfigurableModelTranslation(pydantic.BaseModel):
    language_code: str = 'en'
    value: str = ''

class ConfigurableModelMetadata(pydantic.BaseModel):
    ca_id: str
    ca_name: str
    ca_uuid: str
    name: str
    translations: List[ConfigurableModelTranslation]
    uuid: str

class SmartIntegrationAdditional(pydantic.BaseModel):

    ca_uuids: List[str] = []
    configurable_models_enabled: List[str] = []

    configurable_models_map: Dict[str, List[ConfigurableModelMetadata]] = {}

class ER_SMART_Synchronizer:

    def __init__(self, *args, smart_config=None, er_config=None, das_client=None):


        assert not args, "ER_SMART_Synchronizer does not support positional arguments"

        if das_client:
            self.das_client = das_client
            return

        self.smart_config = smart_config
        self.er_config = er_config or InboundIntegrationConfiguration.objects.get(id=smart_config.additional.get("er_integration_id"))

        self.publisher = get_publisher()
        self.cloud_storage = get_cloud_storage()

        self.smart_client = SmartClient(
            api=smart_config.endpoint,
            username=smart_config.login,
            password=smart_config.password,
            version=smart_config.additional.get("version"),
            use_language_code=smart_config.additional.get("use_language_code", "en"),
        )

        provider_key = self.smart_config.type.slug
        url_parse = urlparse(self.er_config.endpoint)

        # TODO: Replace with er-client
        self.das_client = DasClient(
            service_root=self.er_config.endpoint,
            username=self.er_config.login,
            password=self.er_config.password,
            token=self.er_config.token,
            token_url=f"{url_parse.scheme}://{url_parse.hostname}/oauth2/token",
            client_id="das_web_client",
            provider_key=provider_key,
        )


    def synchronize_datamodel(self):
        # Given a single smart integration, synchronize the datamodels for all the CAs and CMs.
        for ca_uuid in self.smart_config.additional.get('ca_uuids', []):
            ca = self.smart_client.get_conservation_area(ca_uuid=ca_uuid)

            self.push_smart_datamodel_to_earthranger(smart_ca_uuid=ca_uuid, ca=ca)

            for cm in self.smart_config.additional.get('configurable_models_lists', {}).get(ca_uuid):
                cm_uuid = cm.get('uuid')
                # TODO: confirm cm_uuid is member of ca_uuid models list.
                self.push_smart_datamodel_to_earthranger(smart_ca_uuid=ca_uuid, ca=ca, smart_cm_uuid=cm_uuid)



    def push_smart_datamodel_to_earthranger(self, *args, smart_ca_uuid=None, ca=None,
                                            smart_cm_uuid=None):

        assert not args, 'This method does not accept positional arguments'

        dm = self.smart_client.get_data_model(ca_uuid=smart_ca_uuid)

        if smart_cm_uuid:
            cm = self.smart_client.get_configurable_data_model(cm_uuid=smart_cm_uuid)
        else:
            cm = None

        return self.push_smart_ca_datamodel_to_earthranger(dm=dm, smart_ca_uuid=smart_ca_uuid, ca_label=ca.label,
                                                           cm=cm)

    def push_smart_ca_datamodel_to_earthranger(self, *args, dm=None, smart_ca_uuid=None, ca_label=None, cm=None):

        assert not args, 'This method does not accept positional arguments'

        if not dm:
            raise ValueError('dm is required')

        dm_dict = dm.export_as_dict()
        cdm_dict = cm.export_as_dict() if cm else None

        ca_identifier = self.get_identifier_from_ca_label(ca_label)
        event_types = build_earth_ranger_event_types(
            dm=dm_dict, ca_uuid=smart_ca_uuid, ca_identifier=ca_identifier, cdm=cdm_dict
        )

        existing_event_categories = self.das_client.get_event_categories()
        event_category_value = self.calculate_event_category_value(ca_label=ca_identifier, cm_label=getattr(cm, '_name', None))

        # Magic value is 46: Event Category Display should be under 46 characters because EarthRanger
        # will use this value to create a PermissionSet name, which has a max length of 80 characters.
        event_category_display = f"{ca_identifier} {cm._name}" if cm else ca_identifier
        event_category = next(
            (
                x
                for x in existing_event_categories
                if x.get("value") == event_category_value
            ),
            None,
        )

        if not event_category:
            logger.info(
                "Event Category not found in destination ER, creating now ...",
                extra=dict(value=event_category_value, display=event_category_display),
            )

            event_category = dict(value=event_category_value, display=event_category_display)
            self.das_client.post_event_category(event_category)
        self.create_or_update_er_event_types(event_category=event_category, event_types=event_types)
        logger.info(
            f"Finished syncing {len(event_types)} event_types for event_category {event_category.get('display')}"
        )

    @staticmethod
    def calculate_event_category_value(ca_label: str=None, cm_label: str=None):
        translation = {
            ord("["): '', ord("]"): '', ord(" "): "_", ord("-"): "_", ord("/"): "_", ord("("): '', ord(")"): '',
            ord("'"): '', ord('"'): '', ord("."): '', ord(","): '', ord(":"): '', ord(";"): '', ord("&"): '',
            ord("$"): '', ord("#"): '', ord("@"): '', ord("!"): '', ord("?"): '', ord("%"): '', ord("*"): '',
        }

        return ca_label.translate(translation).lower() + "_" + cm_label.translate(translation).lower() if cm_label else ca_label.translate(translation).lower()

    @staticmethod
    def get_identifier_from_ca_label(ca_label: str = ""):
        """
        Expect a string like "Some Name [SONM]"
        Return what's in the brackets (eg. SONM).
        """
        match = re.findall("\[(.*?)\]", ca_label)

        if match:
            return match[-1]

        logger.warning(f"Unable to get identifier from ca_label {ca_label}")
        return ""

    def create_or_update_er_event_types(self, *args, event_category: dict = None, event_types: dict = None):

        assert not args, 'This method does not accept positional arguments'

        # Note: In EarthRanger, EventType.value must be globally unique (not just within category though)
        existing_event_types = self.das_client.get_event_types(
            include_inactive=True, include_schema=True
        )
        try:
            event_type: EREventType
            for event_type in event_types:
                event_type.category = event_category.get("value")
                existing_er_event_type = next(
                    (
                        x
                        for x in existing_event_types
                        if (x.get("value") == event_type.value and x.get('category').get('value') == event_type.category)
                    ),
                    None,
                )
                if existing_er_event_type:
                    if (
                            event_type.is_active != existing_er_event_type.get("is_active")
                            or event_type.display != existing_er_event_type.get("display")
                            or (
                                    event_type.is_active
                                    and event_type.event_schema
                                    and not er_event_type_schemas_equal(
                                json.loads(event_type.event_schema).get("schema"),
                                json.loads(existing_er_event_type.get("schema")).get(
                                    "schema"
                                ),
                            )
                            )
                    ):
                        logger.info(
                            f"Updating ER event type",
                            extra=dict(value=event_type.value),
                        )
                        event_type.id = existing_er_event_type.get("id")
                        try:
                            self.das_client.patch_event_type(
                                event_type.dict(by_alias=True, exclude_none=True)
                            )
                        except Exception as e:
                            logger.error(
                                f" Error occurred during das_client.patch_event_type",
                                extra=dict(event_type=event_type, exception=e),
                            )
                else:
                    logger.info(
                        f"Creating ER event type",
                        extra=dict(
                            value=event_type.value, category=event_type.category
                        ),
                    )
                    try:
                        self.das_client.post_event_type(
                            event_type.dict(by_alias=True, exclude_none=True)
                        )
                    except:
                        logger.error(
                            f" Error occurred during das_client.post_event_type",
                            extra=dict(event_type=event_type),
                        )
        except Exception as e:
            logger.exception(
                f"Unexpected Error occurred during create_or_update_er_event_types",
                extra=dict(event_type=event_type, exception=e),
            )

    def get_er_events(self, *args, config: InboundIntegrationConfiguration):

        assert not args, 'This method does not accept positional arguments'

        i_state = get_earth_ranger_last_poll(integration_id=config.id)

        event_last_poll_at = i_state.event_last_poll_at or datetime.now(
            tz=timezone.utc
        ) - timedelta(days=7)
        current_time = datetime.now(tz=timezone.utc)

        events = parse_obj_as(
            List[EREvent], self.das_client.get_events(updated_since=event_last_poll_at)
        )
        logger.info(f"Pulled {len(events)} events from ER")
        event: EREvent
        for event in events:
            # Exclude events associated to patrols when pushing independent incidents to SMART
            if not event.patrols:
                event.integration_id = config.id
                event.device_id = event.id
                if version.parse(self.smart_client.version) < version.parse("7.5.3"):
                    # stop gap for supporting SMART observation updates
                    try:
                        self.update_event_with_smart_data(event=event)
                    except:
                        logger.error(
                            "Error patching event_type with smart_observation_uuid, event not processed",
                            extra=dict(event_id=event.id, event_title=event.title),
                        )
                for file in event.files:
                    try:
                        self.process_file(file=file)
                    except Exception as e:
                        logger.error(
                            "Failed to download event file",
                            extra=dict(
                                event_serial_number=event.serial_number,
                                file_name=file.get("filename"),
                                error=e,
                            ),
                        )
                logger.info(
                    f"Publishing observation for event",
                    extra=dict(event_id=event.id, event_title=event.title),
                )
                self.publisher.publish(
                    TopicEnum.observations_unprocessed.value, event.dict()
                )
            else:
                logger.info(
                    f"Skipping event {event.serial_number} because it is associated to a patrol"
                )
        i_state.event_last_poll_at = current_time
        set_earth_ranger_last_poll(integration_id=config.id, state=i_state)

    def update_event_with_smart_data(self, event):
        if not event.event_details.get("smart_observation_uuid"):
            # TODO: Populate observation uuid if it does not exist
            smart_observation_uuid = uuid.uuid1()
            event.event_details["smart_observation_uuid"] = str(smart_observation_uuid)
            payload = dict(event_details=event.event_details)
            self.das_client.patch_event(event_id=str(event.id), payload=payload)

    def process_file(self, file):
        file_extension = pathlib.Path(file.get("filename")).suffix
        # use id instead of file_name so that we dont have collisions with other attachments
        file_name = file.get("id") + file_extension
        # check if we have already uploaded to cloud storage
        if not self.cloud_storage.check_exists(file_name=file_name):
            # download from ER server
            url = file.get("url")
            response = self.das_client.get_file(url)
            if response.ok:
                image_uri = self.cloud_storage.upload(response.content, file_name)
            else:
                raise Exception("Error processing file")

    def sync_patrol_datamodel(self):

        smart_ca_uuid=self.smart_config.additional.get("ca_uuids")[0]
        ca = self.smart_client.get_conservation_area(ca_uuid=smart_ca_uuid)

        patrol_data_model = self.smart_client.download_patrolmodel(
            ca_uuid=smart_ca_uuid
        )
        patrol_subjects = get_subjects_from_patrol_data_model(
            pm=patrol_data_model, ca_uuid=smart_ca_uuid
        )

        existing_subjects = parse_obj_as(
            List[ERSubject], self.das_client.get_subjects()
        )
        for subject in patrol_subjects:
            smart_member_id = subject.additional.get("smart_member_id")
            existing_subject_match = next(
                (
                    ex_subject
                    for ex_subject in existing_subjects
                    if ex_subject.additional.get("smart_member_id") == smart_member_id
                ),
                None,
            )

            if existing_subject_match:
                subject.id = existing_subject_match.id
                if not er_subjects_equal(subject, existing_subject_match):
                    pass
                    # TODO: subject updates
                    # das_client.patch_subject(subject.dict())
            else:
                try:
                    ca_identifier = ca.label.split("[")[1].strip("]")
                    subject.name = f"{subject.name} ({ca_identifier})"
                    self.das_client.post_subject(subject.dict(exclude_none=True))
                except Exception:
                    logger.error(
                        f"Error occurred while attempting to create ER subject {subject.dict(exclude_none=True)}"
                    )

    def process_er_patrols(
            self,
            *args,
            patrols: List[ERPatrol],
            integration_id: str,
            patrol_last_poll_at: datetime,
            upper: datetime,
    ):

        assert not args, 'This method does not accept positional arguments'
        patrol: ERPatrol
        for patrol in patrols:
            logger.info(
                f"Beginning processing of ER patrol",
                extra=dict(
                    patrol_id=patrol.id,
                    patrol_serial_num=patrol.serial_number,
                    patrol_title=patrol.title,
                ),
            )
            patrol.integration_id = integration_id
            patrol.device_id = patrol.id

            events_updated_at = []

            publish_observation = True
            extra_dict = dict(
                patrol_id=patrol.id,
                patrol_serial_num=patrol.serial_number,
                patrol_title=patrol.title,
            )

            # active patrols always returned so determine if patrol has any new updates
            updates = patrol.updates
            for seg in patrol.patrol_segments:
                for update in seg.updates:
                    updates.append(update)
                for event in seg.events:
                    events_updated_at.append(event.updated_at)
            max_update = max(events_updated_at + [u.time for u in updates])

            # collect events and track points associated to patrol
            for segment in patrol.patrol_segments:
                if not segment.start_location:
                    # Need start location to pass in coordinates and determine location timezone
                    logger.info(
                        "skipping processing, patrol contains no start location",
                        extra=extra_dict,
                    )
                    publish_observation = False
                    continue

                if not segment.leader:
                    # SMART requires at least one member on patrol leg
                    logger.info(
                        "skipping processing, patrol contains no segment leader",
                        extra=extra_dict,
                    )
                    publish_observation = False
                    continue

                # TODO: Ask ER Core to update endpoint to be able to accept list of event_ids
                for segment_event in segment.events:
                    # Need to get event details for each event since they are not provided in patrol get
                    event_details = parse_obj_as(
                        List[EREvent],
                        self.das_client.get_events(event_ids=segment_event.id),
                    )

                    # process event files
                    for event in event_details:
                        for file in event.files:
                            try:
                                self.process_file(file=file)
                            except Exception as e:
                                logger.error(
                                    "Failed to download event file",
                                    extra=dict(
                                        event_serial_number=event.serial_number,
                                        file_name=file.get("filename"),
                                        error=e,
                                    ),
                                )
                    segment.event_details.extend(event_details)
                    # process event files

                if version.parse(self.smart_client.version) < version.parse("7.5.3"):
                    # stop gap for supporting SMART observation updates
                    for event in segment.event_details:
                        try:
                            self.update_event_with_smart_data(event=event)
                        except:
                            logger.error(
                                "Error patching event_type with smart_observation_uuid, event not processed",
                                extra=dict(event_id=event.id, event_title=event.title),
                            )

                # process patrol files
                for file in patrol.files:
                    try:
                        self.process_file(file=file)
                    except Exception as e:
                        logger.error(
                            "Failed to download patrol file",
                            extra=dict(
                                event_serial_number=patrol.serial_number,
                                file_name=file.get("filename"),
                                error=e,
                            ),
                        )

                # Get track points from subject during time range of patrol
                start = patrol_last_poll_at
                end = upper
                segment.track_points = parse_obj_as(
                    List[ERObservation],
                    self.das_client.get_subject_observations(
                        subject_id=segment.leader.id, start=start, end=end
                    ),
                )

            if max_update < patrol_last_poll_at and \
                    not any(len(seg.track_points) > 0 for seg in patrol.patrol_segments):
                logger.info(
                    "skipping processing, patrol doesn't have updates since last poll",
                    extra=extra_dict,
                )
                continue

            # TODO: Will need to revisit this if we support processing of multiple segments in the future
            if publish_observation:
                logger.info(f"Publishing observation for ER Patrol", extra=extra_dict)
                self.publisher.publish(
                    TopicEnum.observations_unprocessed.value, patrol.dict()
                )

    def get_er_patrols(self, *args, config: InboundIntegrationConfiguration):

        assert not args, 'This method does not accept positional arguments'

        i_state = get_earth_ranger_last_poll(integration_id=config.id)

        lower = i_state.patrol_last_poll_at or datetime.now(
            tz=timezone.utc
        ) - timedelta(days=7)
        # lower = datetime.now(tz=timezone.utc) - timedelta(days=1)
        upper = datetime.now(tz=timezone.utc)

        FILTER_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

        patrol_filter_spec = {
            "date_range": {
                "lower": lower.strftime(FILTER_DATETIME_FORMAT),
                "upper": upper.strftime(FILTER_DATETIME_FORMAT),
            }
        }
        patrols = parse_obj_as(
            List[ERPatrol],
            self.das_client.get_patrols(filter=json.dumps(patrol_filter_spec)),
        )
        logger.info(
            f"Pulled {len(patrols)} patrols from ER",
            extra=dict(
                lower=lower.strftime(FILTER_DATETIME_FORMAT),
                upper=upper.strftime(FILTER_DATETIME_FORMAT),
            ),
        )

        self.process_er_patrols(
            patrols=patrols,
            integration_id=config.id,
            patrol_last_poll_at=lower,
            upper=upper,
        )

        i_state.patrol_last_poll_at = upper
        set_earth_ranger_last_poll(integration_id=config.id, state=i_state)
