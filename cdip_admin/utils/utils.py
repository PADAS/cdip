import logging


logger = logging.getLogger(__name__)


class PubSubDummyClient:
    def create_topic(
            self,
            request=None,
            *,
            name=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using PubSubDummyClient. Topic creation ignored.")
        return None

    def delete_topic(
            self,
            request=None,
            *,
            topic=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using PubSubDummyClient. Topic deletion ignored.")
        return None


class FunctionsDummyClient:
    def create_function(
            self,
            request=None,
            *,
            parent=None,
            function=None,
            function_id=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using FunctionsDummyClient. Function creation ignored.")
        return None

    def update_function(
            self,
            request=None,
            *,
            function=None,
            update_mask=None,
            retry=None,
            timeout=None,
            metadata=(),
    ) -> None:
        logger.warning(f"Using FunctionsDummyClient. Function update ignored.")
        return None

    def delete_function(
            self,
            request=None,
            *,
            name=None,
            retry=None,
            timeout=None,
            metadata= (),
    ) -> None:
        logger.warning(f"Using FunctionsDummyClient. Function deletion ignored.")
        return None
