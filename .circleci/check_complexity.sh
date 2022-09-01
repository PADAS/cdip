#!/bin/bash
set -ue

MAXCC=20
IGNORED_FILES="cdip_admin/cdip_admin/settings.py"

if (git diff --name-only HEAD main | grep .py); then
  echo "Some files were updated and they will be reviewed"
  (git diff --name-only HEAD main | grep .py) | while read -r line ;
  do
    for ignored in "${IGNORED_FILES[@]}"
    do
        if [ "$ignored" != "$line" ] ; then
          echo "Not Found"
          CC=$(radon cc -a $line | grep "complexity" | awk -F "[()]" '{print $2}')
          if (( $(echo "$CC $MAXCC" | awk '{print ($1 > $2)}') )); then
            echo "Code complexity exceeded by $line with a value of $CC"
            exit 1
          fi
        fi
    done
  done
else
  echo "No python files were updated"
fi
