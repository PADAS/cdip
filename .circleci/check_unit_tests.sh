#!/bin/bash
set -ue

pip install -r dependencies/requirements-dev.txt
cd cdip_admin
pytest

# if (git diff --name-only HEAD main | grep .py); then
#   echo "Some files were updated and unit tests will run"
#   cd cdip_admin
#   pytests
# else
#   echo "No python files were updated"
# fi