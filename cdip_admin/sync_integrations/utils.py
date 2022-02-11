from sync_integrations.er_smart_sync import ERSMART_Synchronizer


def run_er_smart_sync_integrations():
    #TODO: Way to associate in portal which integrations should be synced
    smart_integration_id = "114499bc-8689-4e12-adc4-ac9be94eeae0"
    er_integration_id = "9e0d298a-01e0-4bfa-acc3-f0b446037095"
    er_smart_sync = ERSMART_Synchronizer(smart_integration_id=smart_integration_id,
                                         er_integration_id=er_integration_id)
    er_smart_sync.push_smart_ca_data_model_to_er_event_types()
