FROM ubuntu:20.04
MAINTAINER chrisdo@vulcan.com

EXPOSE 8000
ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
ENV LANGUAGE C.UTF-8
ENV DJANGO_SETTINGS_MODULE=cdip_admin.settings
ENV DEBUG=False
ENV SERVICE_NAME=cdip_portal
ENV DB_HOST=host.docker.internal
ENV DJANGO_SILK_ENABLED=True

RUN apt-get update && \
    apt-get -y upgrade && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y \
    git \
    libpq-dev \
    python3-pip \
    curl \
    python3-openssl \
    libssl-dev \
    wget \
    gnupg \
    locales locales-all \
    software-properties-common \
    postgresql-client-12 \
    vim \
    gdal-bin libgdal-dev && \
    apt-get autoremove && \
    pip3 install -U "pip"

WORKDIR /var/www/app
COPY dependencies .
RUN pip3 install -r requirements.txt --no-cache-dir

COPY ./cdip_admin .
COPY ./swagger-fix/index.html /usr/local/lib/python3.8/dist-packages/rest_framework_swagger/templates/rest_framework_swagger/

RUN mkdir -p /var/www/static && \
    python3 manage.py collectstatic --noinput --settings=cdip_admin.local_settings_nodb
CMD ["/var/www/app/start_scripts/start.sh"]
