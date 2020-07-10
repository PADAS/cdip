import requests

from airflow.hooks.http_hook import HttpHook


class CdipHttpHook(HttpHook):
    """
    Minimal extension to Airflow's HttpHook. Allows the hook to be configured with params set when instantiating it,
    instead of getting the information from Airflow's Connection model using a connection_id.
    This will allow our DAGs to configure the CdipHttpHook using config received from cdip admin.
    """

    def __init__(self, baseurl, method='POST', login=None, password=None):
        # set super.connection_id to None
        super().__init__(method, None)
        self.base_url = baseurl
        self.login = login
        self.password = password

    def get_conn(self, headers=None):
        """
        Override HttpHook's get_conn method to configure Session from member variables set in __init__
        (instead of reading from Airflow's Connection model)
        """
        session = requests.Session()
        if self.login:
            session.auth = (self.login, self.password)

        if headers:
            session.headers.update(headers)

        return session


