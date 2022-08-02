import json
import logging
import uuid
from datetime import timezone, datetime, timedelta
from typing import List, Optional
from urllib.parse import urlparse

import pydantic
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


class ER_SMART_Synchronizer:
    def __init__(self, **kwargs):
        smart_integration_id = kwargs.get("smart_integration_id")
        er_integration_id = kwargs.get("er_integration_id")

        smart_config = OutboundIntegrationConfiguration.objects.get(
            id=smart_integration_id
        )
        er_config = InboundIntegrationConfiguration.objects.get(id=er_integration_id)

        if not smart_config or not er_config:
            logger.exception(
                f"No configurations found for integration ids",
                extra=dict(
                    smart_integration_id=smart_integration_id,
                    er_integration_id=er_integration_id,
                ),
            )
            raise Exception("No configurations found for integration ids")

        self.smart_client = SmartClient(
            api=smart_config.endpoint,
            username=smart_config.login,
            password=smart_config.password,
            version=smart_config.additional.get("version"),
            use_language_code="en",
        )

        self.smart_ca_uuids = smart_config.additional.get("ca_uuids")

        provider_key = smart_config.type.slug
        url_parse = urlparse(er_config.endpoint)

        self.das_client = DasClient(
            service_root=er_config.endpoint,
            username=er_config.login,
            password=er_config.password,
            token=er_config.token,
            token_url=f"{url_parse.scheme}://{url_parse.hostname}/oauth2/token",
            client_id="das_web_client",
            provider_key=provider_key,
        )

        self.publisher = get_publisher()

    def push_smart_ca_data_model_to_er_event_types(self, *, smart_ca_uuid, ca):
        dm = self.smart_client.get_data_model(
            ca_uuid=smart_ca_uuid, use_cache=settings.USE_SMART_CACHE
        )
        dm_dict = dm.export_as_dict()

        ca_identifer = self.get_identifier_from_ca_label(ca.label)
        event_types = build_earth_ranger_event_types(
            dm=dm_dict, ca_uuid=smart_ca_uuid, ca_identifier=ca_identifer
        )

        existing_event_categories = self.das_client.get_event_categories()
        event_category_value = self.get_event_category_value_from_ca_label(ca.label)
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
                extra=dict(value=event_category_value, display=ca.label),
            )
            event_category = dict(value=event_category_value, display=ca.label)
            self.das_client.post_event_category(event_category)
        self.create_or_update_er_event_types(event_category, event_types)
        logger.info(
            f"Finished syncing {len(event_types)} event_types for event_category {event_category.get('display')}"
        )

    @staticmethod
    def get_event_category_value_from_ca_label(ca_label: str):
        value = ca_label.replace("[", "")
        value = value.replace("]", "")
        value = value.replace(" ", "_")
        value = value.lower()
        return value

    @staticmethod
    def get_identifier_from_ca_label(ca_label: str):
        try:
            start = ca_label.index("[") + 1
            end = ca_label.index("]")
            return ca_label[start:end]
        except ValueError:
            logger.warning(f"Unable to get identifier from ca_label {ca_label}")
            return ""

    def create_or_update_er_event_types(self, event_category: str, event_types: dict):
        # TODO: would be nice to be able to specify category here.
        #  Currently event_type keys must be globally unique not just within category though
        existing_event_types = self.das_client.get_event_types(
            include_inactive=True, include_schema=True
        )
        try:
            event_type: EREventType
            for event_type in event_types:
                event_type.category = event_category.get("value")
                event_type_match = next(
                    (
                        x
                        for x in existing_event_types
                        if (x.get("value") == event_type.value)
                    ),
                    None,
                )
                if event_type_match:
                    if (
                        event_type.is_active != event_type_match.get("is_active")
                        or event_type.display != event_type_match.get("display")
                        or (
                            event_type.is_active
                            and event_type.event_schema
                            and not er_event_type_schemas_equal(
                                json.loads(event_type.event_schema).get("schema"),
                                json.loads(event_type_match.get("schema")).get(
                                    "schema"
                                ),
                            )
                        )
                    ):
                        logger.info(
                            f"Updating ER event type",
                            extra=dict(value=event_type.value),
                        )
                        event_type.id = event_type_match.get("id")
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

    def get_er_events(self, *, config: InboundIntegrationConfiguration):
        i_state = get_earth_ranger_last_poll(integration_id=config.id)

        event_last_poll_at = i_state.event_last_poll_at or datetime.now(
            tz=timezone.utc
        ) - timedelta(days=7)
        current_time = datetime.now(tz=timezone.utc)

        FILTER_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

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

    def sync_patrol_datamodel(self, *, smart_ca_uuid, ca):
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
        *,
        patrols: List[ERPatrol],
        integration_id: str,
        patrol_last_poll_at: datetime,
        upper: datetime,
    ):
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

            # TODO: Need to handle ones that are newly done but have updates
            # determine if open patrol has any new updates
            if patrol.state != "done":
                updates = patrol.updates
                for seg in patrol.patrol_segments:
                    for update in seg.updates:
                        updates.append(update)
                    for event in seg.events:
                        events_updated_at.append(event.updated_at)
                max_update = max(events_updated_at + [u.time for u in updates])

                if max_update < patrol_last_poll_at:
                    logger.info(
                        "skipping processing, patrol hasn't been updated since last poll",
                        extra=extra_dict,
                    )
                    continue

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
                        "skipping processing, patrol contains no start location",
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
                    segment.event_details.extend(event_details)

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

                # Get track points from subject during time range of patrol
                start = segment.time_range.get("start_time")
                end = segment.time_range.get("end_time")
                if not end:
                    end = upper
                segment.track_points = parse_obj_as(
                    List[ERObservation],
                    self.das_client.get_subject_observations(
                        subject_id=segment.leader.id, start=start, end=end
                    ),
                )
            # TODO: Will need to revisit this if we support processing of multiple segments in the future
            if publish_observation:
                logger.info(f"Publishing observation for ER Patrol", extra=extra_dict)
                self.publisher.publish(
                    TopicEnum.observations_unprocessed.value, patrol.dict()
                )

    def get_er_patrols(self, *, config: InboundIntegrationConfiguration):
        i_state = get_earth_ranger_last_poll(integration_id=config.id)

        lower = i_state.patrol_last_poll_at or datetime.now(
            tz=timezone.utc
        ) - timedelta(days=7)
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
            patrol_last_poll_at=i_state.patrol_last_poll_at,
            upper=upper,
        )

        i_state.patrol_last_poll_at = upper
        set_earth_ranger_last_poll(integration_id=config.id, state=i_state)
        # config.state = json.loads(i_state.json())
        # config.save()
        # logger.debug(f"Saved state to config", extra=dict(state=config.state))
