#!/bin/bash

if [[ -z "$BRANCH" ]]; then
    echo "BRANCH environment variable must be set" 1>&2
    exit 1
fi

mkdir -p "logs/$BRANCH"
for path in log_archives/$BRANCH/*.zip; do
  # if file is nonempty (we create an empty file when a download fails, to prevent further attempts)
  if [ -s "$path" ]; then
    echo Unpacking "$path"
    filename=$(basename "$path")
    # -o to always overwrite, -n to never overwrite
    unzip -n "$path" -d "logs/$BRANCH/${filename%.*}";
  else
    echo Skipping empty file "$path"
  fi
done
