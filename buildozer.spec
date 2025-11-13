[app]

# App name
title = APK URL Extractor

# Package name
package.name = urlextractor

# Package domain
package.domain = com.extractor

# Source code directory
source.dir = .

# Source files
source.include_exts = py,png,jpg,kv,atlas

# Version
version = 1.0

# Requirements
requirements = python3,kivy,kivymd,androguard,pillow

# Android permissions
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# Android API level
android.api = 31
android.minapi = 21

# Android NDK version
android.ndk = 25b

# Android SDK version
android.sdk = 31

# Orientation
orientation = portrait

# App icon (optional - you can add later)
#icon.filename = %(source.dir)s/icon.png

# Presplash (optional)
#presplash.filename = %(source.dir)s/presplash.png

# Android architecture
android.archs = arm64-v8a,armeabi-v7a

# App display name
android.app_name = URL Extractor

# Enable androidx
android.enable_androidx = True

# Gradle dependencies
android.gradle_dependencies = 

# Add Java classes
#android.add_src = 

# Whitelist
android.whitelist = 

[buildozer]

# Log level
log_level = 2

# Display warning if buildozer is run as root
warn_on_root = 1

# Build directory
build_dir = ./.buildozer

# Bin directory
bin_dir = ./bin