#!/bin/bash

mkdir -p logs
for path in log_archives/*.zip; do
  echo Unpacking "$path"
  filename=$(basename "$path")
  # -o to always overwrite, -n to never overwrite
  unzip -n "$path" -d "logs/${filename%.*}";
done
