FROM ubuntu:20.04
MAINTAINER chrisdo@vulcan.com

RUN apt-get update

RUN apt-get install -y \
    git \
    libpq-dev \
    python3-pip \
    curl \
    python3-openssl \
    libssl-dev \
    wget \
    gnupg \
    locales locales-all \
    && apt-get autoremove 

WORKDIR /workspace

ADD requirements.txt /workspace/requirements.txt


RUN pip3 install -U "pip"

RUN pip3 install -r /workspace/requirements.txt --no-cache-dir 

ARG built_version=""

ADD ./cdip_admin /var/www/app

EXPOSE 8000
EXPOSE 5400

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
ENV LANGUAGE C.UTF-8

ENV BUILT_VERSION=${built_version}

ENV DJANGO_SETTINGS_MODULE=cdip_admin.settings

# Default service name
ENV SERVICE_NAME=cdip_portal

WORKDIR /var/www/app

RUN mkdir -p /var/www/static
# Collect static files (using a stub database)
RUN python3 manage.py collectstatic --noinput --settings=cdip_admin.local_settings_nodb

CMD ["/var/www/app/start_scripts/start.sh"]
