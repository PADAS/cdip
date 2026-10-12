from sync_integrations.tracing import PortalTracing


def test_start_span_yields_a_span_that_accepts_attributes_and_events():
    with PortalTracing().start_span("gundi_er_smart_sync.process_event", kind="producer") as span:
        span.set_attribute("is_patrol_event", True)
        span.add_event("gundi_er_smart_sync.event_sent_to_routing")


def test_unknown_kind_falls_back_to_internal():
    with PortalTracing().start_span("x", kind="not-a-kind"):
        pass


def test_build_context_headers_returns_a_dict():
    assert isinstance(PortalTracing().build_context_headers(), dict)
