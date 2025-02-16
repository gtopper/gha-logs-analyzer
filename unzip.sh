#!/bin/bash

BRANCH=development

mkdir -p logs
for path in log_archives/$BRANCH/*.zip; do
  echo Unpacking "$path"
  filename=$(basename "$path")
  # -o to always overwrite, -n to never overwrite
  unzip -n "$path" -d "logs/$BRANCH/${filename%.*}";
done
