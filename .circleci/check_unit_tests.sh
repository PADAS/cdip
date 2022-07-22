#!/bin/bash
set -ue

if (git diff --name-only HEAD main | grep .py); then
  echo "Some files were updated and unit tests will run"
  # run_unit_tests
  echo "TEST ARE DISABELED"
else
  echo "No python files were updated. Unit tests will not run"
fi

run_unit_tests () {
  pip install --upgrade pip
  pip install -r dependencies/requirements.txt
  pip install -r dependencies/requirements-dev.txt
  cd cdip_admin
  pytest
}
