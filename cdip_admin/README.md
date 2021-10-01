## Configuration for running the portal 
+ A .env file will need to be created, and the .env.example file shows the values that will
be needed to successfully run the application.
+ Default database setup is for SqlLite

+ Added Swagger Docs to API
    + Will need to edit index.html file in package
    + venv/Lib/site-packages/rest_framework_swagger/templates/rest_framework_swagger/index.html
    + on line 2 replace {% load staticfiles %} with {% load static %}
    
+ Currently scopes are working for machine to machine communication for the API

+ Internationalization/Localization Setup:
    + On MacOS install brew:
        + In terminal paste: 
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
        + After Install Run: brew install gettext
        + You may need to force link: brew link --force gettext
    + On Windows follow steps at https://docs.djangoproject.com/en/3.0/topics/i18n/translation/#gettext-on-windows
    
    + To Update the Localization files with new items run the following commands:
```shell
        python manage.py makemessages

        python manage.py compilemessages
```

+ Setup Dev to Run Https
    + Run pip install django-sslserver or the requirements-dev.txt file
    + Add "sslserver" in settings.py or preferably create a local_settings.py and override the settings.py
    + Run python manage.py runsslserver --settings=cdip_admin.local_settings
    + Ignore ssl warning or add default Django cert to trusted certs in web browser
    