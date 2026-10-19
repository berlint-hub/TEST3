#!/bin/sh
set -euo pipefail

# Clean build
rm -r ./public || true
hugo build --gc --minify

# Modify icons
pushd ./public
    # Remove unwanted files
    rm -rv \
        android-chrome-192x192.png \
        android-chrome-512x512.png \
        apple-touch-icon.png \
        favicon-16x16.png \
        favicon-32x32.png \
        site.webmanifest \
        tags
    # Remove various tags
    find . -type f -name "*.html" -exec sed -i \
        -e 's/<link rel=icon href=\/favicon-16x16.png type=image\/png sizes=16x16>//g' \
        -e 's/<link rel=icon href=\/favicon-32x32.png type=image\/png sizes=32x32>//g' \
        -e 's/<link rel=apple-touch-icon href=\/apple-touch-icon.png sizes=180x180>//g' \
        -e 's/<link fetchpriority=low href=\/site.webmanifest rel=manifest>//g' \
        {} \;
    # Edit the name of the homepage
    sed -i 's/"lsfg-vk"/"lsfg-vk \xe2\x8b\x85 Lossless Scaling Frame Generation for Linux"/g' index.html
    # Copy favicons
    cp -v logo.svg favicon.svg
    cp -v logo.svg favicon-dark.svg
popd

# Remove (empty) resources
rm -r ./resources
