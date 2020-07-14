## Configuration for running the portal 
+ A .env file will need to be created, and the .env.example file shows the values that will
be needed to successfully run the application.
+ Default database setup is for SqlLite

+ Added Swagger Docs to API
    + Will need to edit index.html file in package
    + venv/Lib/site-packages/rest_framework_swagger/templates/rest_framework_swagger/index.html
    + on line 2 replace {% load staticfiles %} with {% load static %}