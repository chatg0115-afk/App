[app]

# App info
title = APK URL Extractor
package.name = urlextractor
package.domain = com.extractor

# Source
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt

# Version
version = 1.0

# Requirements - UPDATED FOR 2025
requirements = python3,kivy==2.3.0,androguard==4.1.2,pillow,pycryptodome

# Permissions
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# API levels - UPDATED FOR 2025
android.api = 33
android.minapi = 21

# Architecture
android.arch = arm64-v8a

# Orientation
orientation = portrait

# Fullscreen
fullscreen = 0

# Enable AndroidX
android.enable_androidx = True

# Gradle
android.gradle_dependencies = androidx.appcompat:appcompat:1.6.1

# App theme
android.meta_data = android.app.lib_name=urlextractor

[buildozer]

# Log level
log_level = 2

# Build directory
build_dir = .buildozer

# Bin directory
bin_dir = ./bin
