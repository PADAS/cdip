# User Manual
## SMART Integrate Admin Portal

## Table of Contents
1. [View Organization](#view-organization)
2. [View Inbound Integration Configurations](#view-inbound-integrations)
3. [Add a New Inbound Integration Configuration](#add-inbound-integration)
4. [Glossary](#glossary)



## View Organization <a name="view-organization"></a>
    From the left navigation bar click the 'Organization Information' link.
![Left Nav](user_manual_images/view_organization.png)



## View Inbound Integration Configurations <a name="view-inbound-integration"></a>

    To see a list of available inbound integrations 'Inbound Integrations' link.
![Left Nav](user_manual_images/view_inbound_integrations.png)

## Add a New Inbound Integration Configuration <a name="add-inbound-integration"></a>

    1. To add a new inbound integration configuration 'Configure Integration' link.
![Left Nav](user_manual_images/view_inbound_integrations.png)

    2. Fill out the form with the appropriate information.
<img src="user_manual_images/add_inbound_integration.png" width="500" />

        a. Type - Select the type of Integration you are configuraing. For Example: Savannah Tracker
        b. Owner - Assign who what organization an integration corresponds to. For Example: Grumeti
        c. Endpoint - Url of a given integration API (External)
        d. State - A JSON blob that depicts the state of the configuration. This also contains any custom information 
        an integration may need.
        e. Login - The username for the credentials of the integration API if needed.
        f. Password - The password for the credentials of the integration API if needed.
        g. Token - The token for the credentials of the integration API if needed.
        h. Destinations - The outbound destinations for a given integration. For example: Earthranger - Matla Mamba
        

## Glossary <a name="glossary"></a>
Define some things