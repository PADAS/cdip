# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- Connections no longer show as **Unhealthy** because of a shared destination's health. A destination integration is shared across every connection that routes to it, so an unhealthy destination previously marked all of its connections Unhealthy even when their own provider had no errors (the destination's errors live under the destination, not the connection). A healthy provider with an unhealthy or disabled shared destination is now surfaced as **Needs review** instead, in both `ConnectionRetrieveSerializer.get_status` and `filter_connections_by_status` (the `?status=` filter and the unhealthy-connections email).

### Added

- `recalculate_integration_statuses` management command — runs the same health calculation as the hourly "Calculate Integration Statuses" beat task on demand. Recalculates all integrations by default, or specific ones via `--integration-id` (repeatable); `--async` enqueues the Celery task instead of running inline.
