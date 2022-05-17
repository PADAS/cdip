import datetime
from typing import NamedTuple
import tempfile

import dateutil.parser
import pytz
from django.core.management.base import BaseCommand
from django.conf import settings

# This is just a sample command to use as a guide for creating other commands.


class Command(BaseCommand):
    help = "A sample command with some arguments."

    def add_arguments(self, parser):
        parser.add_argument("--some_argument", type=str, help="A sample argument")
        parser.add_argument("--a_date_argument", type=str, help="A date argument")
        parser.add_argument(
            "--some_boolean", action="store_true", help="A sample boolean argument"
        )

    def handle(self, *args, **options):

        if options["some_boolean"]:
            print("You enabled some_boolean")
        if options["a_date_argument"]:
            a_date = dateutil.parser.parse(options["a_date_argument"])
            if not a_date.tzinfo:
                a_date = a_date.replace(tzinfo=pytz.UTC)
            print(f"You gave me a_date_argument={a_date.isoformat()}")
