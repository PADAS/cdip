ARG PY_VERSION=3.9-alpine
FROM python:${PY_VERSION}
MAINTAINER devops@earthranger.com

ARG APPLICATION_PATH=/app
ARG USERNAME="appuser"
ARG USER_ID="1001"

ENV SERVICE_NAME=cdip_portal
ENV DJANGO_SETTINGS_MODULE=cdip_admin.settings
ENV DEBUG=False
WORKDIR ${APPLICATION_PATH}


COPY dependencies/requirements.txt ${APPLICATION_PATH}
RUN apk add --no-cache --virtual .build-deps \
    postgresql-dev gcc python3-dev musl-dev libffi-dev cargo openssl-dev && \
    apk add --no-cache libpq && \
    addgroup -g ${USER_ID} ${USERNAME} && \
    adduser -S -u ${USER_ID} -G ${USERNAME} ${USERNAME} && \
    chown ${USERNAME}:${USERNAME} -R ${APPLICATION_PATH} && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del .build-deps

COPY --chown=appuser:appuser ./cdip_admin .
EXPOSE 8000

CMD ["/app/start_scripts/start.sh"]

# use apt-get update and install in the same RUN command: http://lenguyenthedat.com/docker-cache/
# This will be updated since we are moving to alpine distribution
# RUN apt-get update && \
#     apt-get -y upgrade && \
#     DEBIAN_FRONTEND=noninteractive \
#     apt-get install -y \
#     git \ # production image should not have git
#     libpq-dev \  # this will be installed just on the build process
#     python3-pip \ # python image has already loaded pip
#     curl \ # Open to discuss the need of curl
#     python3-openssl \ # python images has this pre-loaded
#     libssl-dev \ # This should only exist on the build process
#     wget \ # Open to disscuss
#     gnupg \ # Open to disucss
#     locales locales-all \ # Production image should not have this
#     software-properties-common \ # There is no need of this
#     postgresql-client-12 \ # This will replaced by
#     vim \ # Production images doesn't need vim
#     && apt-get autoremove


# Open to discuss all this
# Use ubuntugis/ppa for bionic since it's not available for 20.04 (focal) yet.
# RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 089EBE08314DF160
# RUN /bin/sh -c 'echo "deb http://ppa.launchpad.net/ubuntugis/ppa/ubuntu bionic main" >> /etc/apt/sources.list.d/ubuntugis.list'
# RUN apt-get update
# RUN apt-get update && \
#     apt-get -y install gdal-bin libgdal-dev
# RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal
# RUN export C_INCLUDE_PATH=/usr/include/gdal
# RUN pip3 install GDAL==$(gdal-config --version)

# WORKDIR /workspace

# ADD dependencies/requirements.txt /workspace/requirements.txt

# RUN pip3 install -U "pip"

# RUN pip3 install -r /workspace/requirements.txt --no-cache-dir

# ARG built_version=""

# ADD ./cdip_admin /var/www/app
# ADD ./swagger-fix/index.html /usr/local/lib/python3.8/dist-packages/rest_framework_swagger/templates/rest_framework_swagger/

# EXPOSE 8000

# ENV LC_ALL C.UTF-8
# ENV LANG C.UTF-8
# ENV LANGUAGE C.UTF-8

# ENV BUILT_VERSION=${built_version}

# ENV DJANGO_SETTINGS_MODULE=cdip_admin.settings
# ENV DEBUG=False

# Default service name
# ENV SERVICE_NAME=cdip_portal

# if connecting to db running on localhost
# ENV DB_HOST=host.docker.internal

# WORKDIR /var/www/app

# RUN mkdir -p /var/www/static
# I would like to know more about this
# Collect static files (using a stub database)
# RUN python3 manage.py collectstatic --noinput --settings=cdip_admin.local_settings_nodb

# CMD ["/var/www/app/start_scripts/start.sh"]
